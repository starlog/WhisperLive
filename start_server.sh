#!/bin/bash
source /home/felix/anaconda3/etc/profile.d/conda.sh
conda activate whisperlive
python run_server.py --port 9090 --backend faster_whisper
