"""MiDaS v2.1 (MidasNet, ResNeXt-101 32x8d WSL encoder).

Vendored from https://github.com/isl-org/MiDaS (commit 454597711a62, midas/midas_net.py and
midas/blocks.py), MIT License, Copyright (c) 2019 Intel ISL. Changes: the encoder is built from
torchvision's resnext101_32x8d without weights (same architecture as the WSL hub model), so no
torch.hub download happens; all weights come from midas_v21_384.pt. The forward pass, including
the in-place ReLU in ResidualConvUnit that the released weights were trained with, is unchanged.

Output: relative inverse depth (disparity), larger = closer, shape (B, H, W), always float32
(the output head runs outside autocast).
"""

import torch
import torch.nn as nn
from torchvision.models import resnext101_32x8d


class Interpolate(nn.Module):
    def __init__(self, scale_factor, mode, align_corners=False):
        super().__init__()
        self.interp = nn.functional.interpolate
        self.scale_factor = scale_factor
        self.mode = mode
        self.align_corners = align_corners

    def forward(self, x):
        return self.interp(x, scale_factor=self.scale_factor, mode=self.mode,
                           align_corners=self.align_corners)


class ResidualConvUnit(nn.Module):
    def __init__(self, features):
        super().__init__()
        self.conv1 = nn.Conv2d(features, features, kernel_size=3, stride=1, padding=1, bias=True)
        self.conv2 = nn.Conv2d(features, features, kernel_size=3, stride=1, padding=1, bias=True)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        out = self.relu(x)
        out = self.conv1(out)
        out = self.relu(out)
        out = self.conv2(out)
        return out + x


class FeatureFusionBlock(nn.Module):
    def __init__(self, features):
        super().__init__()
        self.resConfUnit1 = ResidualConvUnit(features)
        self.resConfUnit2 = ResidualConvUnit(features)

    def forward(self, *xs):
        output = xs[0]
        if len(xs) == 2:
            output += self.resConfUnit1(xs[1])
        output = self.resConfUnit2(output)
        return nn.functional.interpolate(output, scale_factor=2, mode="bilinear",
                                         align_corners=True)


def _make_scratch(in_shape, out_shape):
    scratch = nn.Module()
    for i, channels in enumerate(in_shape, start=1):
        setattr(scratch, f"layer{i}_rn",
                nn.Conv2d(channels, out_shape, kernel_size=3, stride=1, padding=1, bias=False))
    return scratch


def _make_resnet_backbone(resnet):
    pretrained = nn.Module()
    pretrained.layer1 = nn.Sequential(resnet.conv1, resnet.bn1, resnet.relu, resnet.maxpool,
                                      resnet.layer1)
    pretrained.layer2 = resnet.layer2
    pretrained.layer3 = resnet.layer3
    pretrained.layer4 = resnet.layer4
    return pretrained


class MidasNet(nn.Module):
    def __init__(self, features=256, non_negative=True):
        super().__init__()
        self.pretrained = _make_resnet_backbone(resnext101_32x8d(weights=None))
        self.scratch = _make_scratch([256, 512, 1024, 2048], features)
        self.scratch.refinenet4 = FeatureFusionBlock(features)
        self.scratch.refinenet3 = FeatureFusionBlock(features)
        self.scratch.refinenet2 = FeatureFusionBlock(features)
        self.scratch.refinenet1 = FeatureFusionBlock(features)
        self.scratch.output_conv = nn.Sequential(
            nn.Conv2d(features, 128, kernel_size=3, stride=1, padding=1),
            Interpolate(scale_factor=2, mode="bilinear"),
            nn.Conv2d(128, 32, kernel_size=3, stride=1, padding=1),
            nn.ReLU(True),
            nn.Conv2d(32, 1, kernel_size=1, stride=1, padding=0),
            nn.ReLU(True) if non_negative else nn.Identity(),
        )

    def forward(self, x):
        layer_1 = self.pretrained.layer1(x)
        layer_2 = self.pretrained.layer2(layer_1)
        layer_3 = self.pretrained.layer3(layer_2)
        layer_4 = self.pretrained.layer4(layer_3)

        layer_1_rn = self.scratch.layer1_rn(layer_1)
        layer_2_rn = self.scratch.layer2_rn(layer_2)
        layer_3_rn = self.scratch.layer3_rn(layer_3)
        layer_4_rn = self.scratch.layer4_rn(layer_4)

        path_4 = self.scratch.refinenet4(layer_4_rn)
        path_3 = self.scratch.refinenet3(path_4, layer_3_rn)
        path_2 = self.scratch.refinenet2(path_3, layer_2_rn)
        path_1 = self.scratch.refinenet1(path_2, layer_1_rn)

        # Output head in fp32 even under autocast: values are in the thousands, where bf16 steps
        # by 16-32. Without autocast this is identical to upstream.
        with torch.autocast(device_type=x.device.type, enabled=False):
            out = self.scratch.output_conv(path_1.float())
        return torch.squeeze(out, dim=1)


def extract_state_dict(obj):
    """Accept a plain state dict, MiDaS' {'model', 'optimizer'} format, or our checkpoints."""
    if isinstance(obj, dict):
        for key in ("model", "comics2depth_state_dict", "state_dict"):
            if key in obj and isinstance(obj[key], dict):
                return obj[key]
    return obj


def load_midas(path, map_location="cpu") -> MidasNet:
    model = MidasNet()
    state = torch.load(path, map_location=map_location, weights_only=True)
    model.load_state_dict(extract_state_dict(state), strict=True)
    return model
