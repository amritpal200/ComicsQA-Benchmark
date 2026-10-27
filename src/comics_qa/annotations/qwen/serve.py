"""Print or launch conservative vLLM presets for Qwen3-VL-32B-Instruct."""
import argparse
import json
import os
import shlex
import shutil

BASE = 'Qwen/Qwen3-VL-32B-Instruct'
# max sequences, context, max batched tokens; starting points, not measured guarantees.
PRESETS = {
    '95gb': (BASE, 16, 8192, 8192),
    '65gb': (BASE + '-FP8', 16, 8192, 8192),
    '46gb': (BASE + '-FP8', 8, 8192, 4096),
    '24gb': ('cyankiwi/Qwen3-VL-32B-Instruct-AWQ-4bit', 1, 4096, 2048),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PRESETS, default='46gb')
    parser.add_argument('--model', help='Override checkpoint, e.g. local weights')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--tensor-parallel-size', type=int, default=1)
    parser.add_argument('--cpu-offload-gb', type=float, default=0)
    parser.add_argument('--print-only', action='store_true')
    args, extra = parser.parse_known_args()
    model, seqs, context, tokens = PRESETS[args.profile]
    if args.tensor_parallel_size < 1 or args.cpu_offload_gb < 0:
        parser.error('Invalid parallelism/offload setting')
    command = ['vllm', 'serve', args.model or model, '--host', '127.0.0.1', '--port', str(args.port),
               '--tensor-parallel-size', str(args.tensor_parallel_size),
               '--gpu-memory-utilization', '0.90', '--max-model-len', str(context),
               '--max-num-seqs', str(seqs), '--max-num-batched-tokens', str(tokens),
               '--limit-mm-per-prompt', json.dumps({'image': 1, 'video': 0}),
               '--mm-processor-cache-gb', '0', '--enable-chunked-prefill',
               '--mm-processor-kwargs', json.dumps({'max_pixels': 786432 if args.profile == '24gb' else 1572864})]
    if args.profile == '24gb':
        command += ['--enforce-eager']
    if args.cpu_offload_gb:
        command += ['--cpu-offload-gb', str(args.cpu_offload_gb)]
    command += extra
    print('OMP_NUM_THREADS=1 ' + shlex.join(command), flush=True)
    if not args.print_only:
        if not shutil.which('vllm'):
            parser.error('Install the server group: uv sync --group server')
        os.environ.setdefault('OMP_NUM_THREADS', '1')
        os.execvp(command[0], command)


if __name__ == '__main__':
    main()
