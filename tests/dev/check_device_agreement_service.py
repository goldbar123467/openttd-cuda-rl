#!/usr/bin/env python3
"""Native development-wire integration check; requires an explicit build/package."""
import argparse
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/dev'))
from local import capture_source, host, source_identity, write_json
from verify_device_agreement import TrainerClient, import_package, inspect, package_hashes, sha256
from m08_trainer_client import M08TrainerClientError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trainer', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda:0'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    hashes, manifest = package_hashes(args.package)
    record = dict(kind='v1-device-agreement-service-test', status='running', command=sys.argv,
                  source=source_identity(), source_archive=capture_source(output/'source'), host=host(),
                  device=args.device, trainer_sha256=sha256(args.trainer), package_hashes=hashes, checks=[])
    client = None
    def start(architecture=manifest['architecture']):
        return TrainerClient.start(args.trainer.resolve(), architecture=architecture, device=args.device,
            run_seed=925, rollout_length=4, environment_count=1, minibatch_size=4, optimization_epochs=1,
            diagnostic_root=output/'diagnostics')
    def reject(function, text):
        try:
            function()
        except M08TrainerClientError as exc:
            assert text in str(exc), str(exc)
        else:
            raise AssertionError('Native service accepted forbidden request')
    try:
        client = start()
        for batch in (0, 65):
            reject(lambda: client._request(9, struct.pack('<IB', batch, 1)), 'batch')
            record['checks'].append(f'inspect-batch-{batch}-rejected')
        reject(lambda: client._request(9, struct.pack('<IB', 1, 0)), 'deterministic')
        record['checks'].append('sampled-inspect-rejected')
        identity = import_package(client, args.package.resolve())
        assert identity['package_id'] == args.package.name and identity['model_sha256'] == hashes['model.pt']
        for batch in (1, 64):
            structured, spatial, masks = [[.25]*256]*batch, [[.25]*32768]*batch, [[1]+[0]*40]*batch
            rows = inspect(client, structured, spatial, masks)
            assert all(row['action'] == 0 and row['probabilities'] == [1.]+[0.]*40 for row in rows)
            record['checks'].append(f'import-inspect-batch-{batch}-single-choice')
        for kind in (2, 3, 5):
            reject(lambda: client._request(kind, b''), 'inference only')
            record['checks'].append(f'imported-request-{kind}-rejected')
        client.close()
        client = None
        for kind in (6, 10):
            client = start()
            import_package(client, args.package.resolve())
            reject(lambda: client._request(kind, b''), 'inference only')
            assert client.process.wait(timeout=30) == 1
            client.abort()
            client = None
            record['checks'].append(f'imported-request-{kind}-rejected-and-exited')
        wrong = 'spatial-cnn-v1' if manifest['architecture'] != 'spatial-cnn-v1' else 'structured-mlp-v1'
        client = start(wrong)
        reject(lambda: import_package(client, args.package.resolve()), 'architecture mismatch')
        assert client.process.wait(timeout=30) == 1
        client.abort()
        client = None
        record['checks'].append('wrong-architecture-import-rejected-and-exited')
        assert package_hashes(args.package)[0] == hashes
        record['status'] = 'passed'
        print(json.dumps({k: record[k] for k in ('status', 'device', 'checks')}))
    except BaseException as exc:
        record.update(status='failed', error=str(exc))
        raise
    finally:
        if client is not None:
            client.abort()
        write_json(output/'verification.json', record)


if __name__ == '__main__':
    main()
