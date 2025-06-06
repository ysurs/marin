"""
reorganize.py

Script for reorganizing the `marin-data` GCS bucket (transferring files to `marin-us-central2`) via the Google Cloud
Storage Transfer Service API.

Mappings (before / after) are defined as a top-level `*MAPPINGS` dictionary, which auto-generates the Storage Transfer
configuration, then programmatically creates & launches each job.

Reference :: https://cloud.google.com/storage-transfer/docs/manifest
"""

import json

from google.cloud import storage_transfer

# Defines each Transfer Job as a mapping :: `job_name` -> (`src_bucket_root`, `destination_bucket_root`)
# fmt: off
RAW_TRANSFER_JOB_MAPPINGS = {
    # === External Semi-Formatted (dolma, datacomp, fineweb-edu) ===
    "raw-dolma (v1.7)": (
        {"bucket_name": "marin-data", "path": "raw/dolma/dolma-v1.7/"},
        {"bucket_name": "marin-us-central2", "path": "raw/dolma/v1.7/"},
    ),

    "raw-dclm (v2024-07-09-baseline-dedup)": (
        {"bucket_name": "marin-data", "path": "datacomp/dclm-baseline-dedup-07-09/"},
        {"bucket_name": "marin-us-central2", "path": "raw/dclm/v2024-07-09-baseline-dedup/"},
    ),

    "raw-fineweb-edu (#5b89d1e)": (
        {
            "bucket_name": "marin-data",
            "path": (
                "raw/fineweb-edu/huggingface.co/datasets/HuggingFaceFW/"
                "resolve/5b89d1ea9319fe101b3cbdacd89a903aca1d6052/data/"
            ),
        },
        {"bucket_name": "marin-us-central2", "path": "raw/fineweb-edu/5b89d1e/"},
    ),

    # === Raw Data ===
    "raw-algebraic-stack (v2023-10-13)": (
        {"bucket_name": "marin-data", "path": "raw/algebraic-stack/"},
        {"bucket_name": "marin-us-central2", "path": "raw/algebraic-stack/v2023-10-13/"},
    ),

    # ar5iv is from: https://sigmathling.kwarc.info/resources/ar5iv-dataset-2024/
    "raw-ar5iv (v04.2024)": (
        {"bucket_name": "marin-data", "path": "raw/arxiv/data.fau.de/"},
        {"bucket_name": "marin-us-central2", "path": "raw/ar5iv/v04.2024/"}
    ),

    "raw-fineweb (#cd85054)": (
        {"bucket_name": "marin-data", "path": "raw/fineweb/fw-v1.0/"},
        {"bucket_name": "marin-us-central2", "path": "raw/fineweb/cd85054/"}
    ),

    "raw-falcon-refinedweb (#c735840)": (
        {
            "bucket_name": "marin-data",
            "path": (
                "raw/huggingface.co/datasets/tiiuae/falcon-refinedweb/"
                "resolve/c735840575b629292b41da8dde11dcd523d4f91c/data/"
            ),
        },
        {"bucket_name": "marin-us-central2", "path": "raw/falcon-refinedweb/c735840/"},
    ),

    # Adding `legal` prefix in case folks are not familiar with individual corpora
    "raw-legal-edgar (v1.0 - #f7d3ba7)": (
        {
            "bucket_name": "marin-data",
            "path": (
                "raw/huggingface.co/datasets/eloukas/edgar-corpus/resolve/f7d3ba73d65ff10194a95b84c75eb484d60b0ede/"
            ),
        },
        {"bucket_name": "marin-us-central2", "path": "raw/legal-edgar/f7d3ba7/"},
    ),

    "raw-legal-hupd (f570a84)": (
        {"bucket_name": "marin-data", "path": "raw/huggingface.co/datasets/HUPD/hupd/resolve/main/data/"},
        {"bucket_name": "marin-us-central2", "path": "raw/legal-hupd/f570a84/"},
    ),

    "raw-legal-multi-legal-wikipedia-filtered (#483f6c8)": (
        {
            "bucket_name": "marin-data",
            "path": "raw/huggingface.co/datasets/joelniklaus/MultiLegalPileWikipediaFiltered/resolve/main/data/",
        },
        {"bucket_name": "marin-us-central2", "path": "raw/legal-multi-legal-wikipedia-filtered/483f6c8/"},
    ),

    "raw-legal-open-australian-legal-corpus (#66e7085)": (
        {
            "bucket_name": "marin-data",
            "path": (
                "raw/huggingface.co/datasets/umarbutler/open-australian-legal-corpus/"
                "resolve/66e7085ff50b8d71d3089efbf60e02ef5b53cf46/"
            ),
        },
        {"bucket_name": "marin-us-central2", "path": "raw/legal-open-australian-legal-corpus/66e7085/"},
    ),

    # Adding `instruct` prefix in case folks are not familiar with individual corpora
    "raw-instruct-tulu-v2-sft (#6248b17)": (
        {
            "bucket_name": "marin-data",
            "path": (
                "raw/instruct/huggingface.co/datasets/allenai/tulu-v2-sft-mixture/"
                "resolve/6248b175d2ccb5ec7c4aeb22e6d8ee3b21b2c752/data/"
            ),
        },
        {"bucket_name": "marin-us-central2", "path": "raw/instruct-tulu-v2-sft/6248b17/"},
    ),

    "raw-pubmed-abstracts (v2023-12-14)": (
        {"bucket_name": "marin-data", "path": "raw/pubmed/pubmed_abstracts/"},
        {"bucket_name": "marin-us-central2", "path": "raw/pubmed-abstracts/v2023-12-14/"}
    ),

    "raw-pubmed-central (v2023-12-18)": (
        {"bucket_name": "marin-data", "path": "raw/pubmed/pubmed_central/"},
        {"bucket_name": "marin-us-central2", "path": "raw/pubmed-central/v2023-12-18/"}
    ),

    "raw-slim-pajama (#2d0accd)": (
        {"bucket_name": "marin-data", "path": "raw/slim-pajama/2d0accdd/SlimPajama-627B/"},
        {"bucket_name": "marin-us-central2", "path": "raw/slim-pajama/2d0accd/"},
    ),

    "raw-stackexchange (v2024-04-02)": (
        {"bucket_name": "marin-data", "path": "raw/stackexchange/archive.org/download/stackexchange/"},
        {"bucket_name": "marin-us-central2", "path": "raw/stackexchange/v2024-04-02/"},
    ),

    "raw-wikipedia (v2024-05-01)": (
        {"bucket_name": "marin-data", "path": "raw/wikipedia/"},
        {"bucket_name": "marin-us-central2", "path": "raw/wikipedia/v2024-05-01/"}
    ),
}
# fmt: on

# === Set `TRANSFER_JOB_MAPPINGS` ===
TRANSFER_JOB_MAPPINGS = RAW_TRANSFER_JOB_MAPPINGS
TRANSFER_JOB_PREFIX = "raw"


def reorganize() -> None:
    print("[*] Reorganizing GCS Bucket `gs://marin-data` -> `gs://marin-us-central2`")
    client = storage_transfer.StorageTransferServiceClient()

    # Iterate though Transfer Job Mappings =>> fire off transfers!
    transfer_job_operations = {}
    for transfer_job_name, (gs_src, gs_sink) in TRANSFER_JOB_MAPPINGS.items():
        assert gs_src["bucket_name"] == "marin-data", f"Unexpected `src` bucket name: {gs_src['bucket_name']}"
        assert gs_sink["bucket_name"] == "marin-us-central2", f"Unexpected `sink` bucket name: {gs_sink['bucket_name']}"

        request = storage_transfer.CreateTransferJobRequest(
            {
                "transfer_job": {
                    "project_id": "hai-gcp-models",
                    "description": f"Reorganization Transfer Job for {transfer_job_name}",
                    "status": storage_transfer.TransferJob.Status.ENABLED,
                    "transfer_spec": {"gcs_data_source": gs_src, "gcs_data_sink": gs_sink},
                }
            }
        )

        # Create Job and Run
        #   => `creation_request` =>> Specifies Job, creates new "entry" in `console.cloud.google.com/jobs/transferJobs`
        #   => `run_response` =>> Actually invokes the transfer operation and tracks status
        creation_request = client.create_transfer_job(request)
        run_response = client.run_transfer_job({"job_name": creation_request.name, "project_id": "hai-gcp-models"})

        # Add Job Metadata to Trackers
        #   => Check https://console.cloud.google.com/transfer/jobs/<transfer_job_id>
        transfer_job_operations[transfer_job_name] = {
            "transfer_job_id": creation_request.name,
            "run_operation": run_response,
        }

    # Wait until all `run_operations` are done!
    try:
        still_running = True
        while still_running:
            running_jobs = [job for job in transfer_job_operations.values() if job["run_operation"].running()]
            still_running = len(running_jobs) > 0

            print(f"[*] {len(running_jobs)} / {len(transfer_job_operations)} Transfer Jobs are still in progress!")

    finally:
        print("[*] Serializing `transfer_job_operations` to `scripts/gcs-reorganization/transfer.json`")
        with open(f"scripts/gcs-reorganization/{TRANSFER_JOB_PREFIX}-transfer.json", "w") as f:
            json.dump(
                {
                    k: {"transfer_job_id": v["transfer_job_id"], "run_operation_id": v["run_operation"].operation.name}
                    for k, v in transfer_job_operations.items()
                },
                f,
                indent=2,
            )


if __name__ == "__main__":
    reorganize()
