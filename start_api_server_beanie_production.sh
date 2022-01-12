#!/bin/bash

source ~/miniconda3/etc/profile.d/conda.sh  # finds command conda
conda activate cov2k_api_v1

# define utility functions
timestamp() {
  TZ=Europe/Rome date +"%Y_%m_%d__%H_%M_%S" # current time
}

cd /home/alfonsi/cov2k-services/cov2k_api_v1.2

ROOT_PATH=/cov2k/api
echo $ROOT_PATH > root_path.txt
mkdir -p logs
uvicorn main_beanie:app --host=localhost --root-path ${ROOT_PATH} 2>&1 | tee "logs/log_$(timestamp).txt"

