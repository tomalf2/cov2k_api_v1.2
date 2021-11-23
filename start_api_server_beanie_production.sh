#!/bin/bash

source ~/miniconda3/etc/profile.d/conda.sh  # finds command conda
conda activate cov2k_api_v1

uvicorn main_beanie:app --host=localhost --root-path /cov2k/api

