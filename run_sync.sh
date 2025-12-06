#!/bin/bash
# fájl: ~/Programs/ekreta-caldav/run_sync.sh

# Beállítjuk a conda környezetet
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ekreta

# Futattjuk a Python szkriptet
python /home/herkaba/Programs/ekreta-caldav/sync.py >> /home/herkaba/Programs/ekreta-caldav/sync.log 2>&1
