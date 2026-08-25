#!/bin/bash


IMAGE=ncsuswat/flashfuzz:torch2.2-fuzz


PROJECT_DIR=$(pwd)


FUZZ=/root/fuzz/third_party/FlashFuzz/testharness/torch_cpu/torch.reshape/fuzz


CRASH_DIR=$PROJECT_DIR/results/raw/EXP007/baseline/torch.reshape/run_1/fuzz/artifacts


for crash in $CRASH_DIR/crash-*;
do

echo "===================================="
echo "Testing $crash"
echo "===================================="


REL_PATH=${crash#$PROJECT_DIR}


docker run --rm \
-v $PROJECT_DIR:/root/fuzz \
$IMAGE \
bash -c "
$FUZZ /root/fuzz$REL_PATH
"


done
