"""CycleGAN generator/discriminator used by ComicsDepth.

Reconstructed from the inline copies in upstream cyclegan_natural_comics_add_text_train.py and
depth_add_text_ignoretext_train.py (themselves based on eriklindernoren/PyTorch-GAN). The
upstream models/models.py module was never published; the inline copies load its checkpoints,
so the architecture is the same. Generators take and return images in [0, 1] (Sigmoid output).
"""

import torch.nn as nn


class ResidualBlock(nn.Module):
    def __init__(self, in_features):
        super().__init__()
        self.block = nn.Sequential(
            nn.ReflectionPad2d(1),
            nn.Conv2d(in_features, in_features, 3),
            nn.InstanceNorm2d(in_features),
            nn.ReLU(inplace=True),
            nn.ReflectionPad2d(1),
            nn.Conv2d(in_features, in_features, 3),
            nn.InstanceNorm2d(in_features),
        )

    def forward(self, x):
        return x + self.block(x)


class GeneratorResNet(nn.Module):
    def __init__(self, in_channels=3, out_channels=3, num_residual_blocks=8):
        super().__init__()
        out_features = 64
        model = [
            nn.ReflectionPad2d(3),
            nn.Conv2d(in_channels, out_features, 7),
            nn.InstanceNorm2d(out_features),
            nn.ReLU(inplace=True),
        ]
        in_features = out_features
        for _ in range(2):
            out_features *= 2
            model += [
                nn.Conv2d(in_features, out_features, 3, stride=2, padding=1),
                nn.InstanceNorm2d(out_features),
                nn.ReLU(inplace=True),
            ]
            in_features = out_features
        model += [ResidualBlock(out_features) for _ in range(num_residual_blocks)]
        for _ in range(2):
            out_features //= 2
            model += [
                nn.Upsample(scale_factor=2),
                nn.Conv2d(in_features, out_features, 3, stride=1, padding=1),
                nn.InstanceNorm2d(out_features),
                nn.ReLU(inplace=True),
            ]
            in_features = out_features
        model += [nn.ReflectionPad2d(3), nn.Conv2d(out_features, out_channels, 7), nn.Sigmoid()]
        self.model = nn.Sequential(*model)

    def forward(self, x):
        return self.model(x)


class Discriminator(nn.Module):
    """PatchGAN discriminator; output is (B, 1, H/16, W/16)."""

    def __init__(self, input_shape=(3, 384, 384)):
        super().__init__()
        channels, height, width = input_shape
        self.output_shape = (1, height // 2 ** 4, width // 2 ** 4)

        def block(in_filters, out_filters, normalize=True):
            layers = [nn.Conv2d(in_filters, out_filters, 4, stride=2, padding=1)]
            if normalize:
                layers.append(nn.InstanceNorm2d(out_filters))
            layers.append(nn.LeakyReLU(0.2, inplace=True))
            return layers

        self.model = nn.Sequential(
            *block(channels, 64, normalize=False),
            *block(64, 128),
            *block(128, 256),
            *block(256, 512),
            nn.ZeroPad2d((1, 0, 1, 0)),
            nn.Conv2d(512, 1, 4, padding=1),
        )

    def forward(self, img):
        return self.model(img)
