#!/bin/bash

set -e

BASE_DIR=$(pwd)

RESULT_DIR=$BASE_DIR/results


APIS=(
torch.add
torch.mul
torch.matmul
torch.mm
torch.addmm
torch.exp
torch.relu
torch.sigmoid
torch.softmax
torch.tanh
)


TIME=600


for API in "${APIS[@]}"
do

echo "Running $API"


cd $BASE_DIR/$API


rm -rf coverage_data


python3 coverage_fuzzing.py \
    --api $API \
    --interval 60 \
    --max-time $TIME \
    --coverage-dir coverage_data



for INTERVAL_DIR in coverage_data/*/
do

    NAME=$(basename $INTERVAL_DIR)


    cd $INTERVAL_DIR


    llvm-profdata merge \
        -sparse \
        ${API}.profraw \
        -o ${API}.profdata


    python3 /workspace/FlashFuzz/scripts/get_coverage_results.py \
        --binary /root/pytorch/build-fuzz/lib/libtorch_cpu.so \
        --dll torch \
        --require aten/src/ATen/native \
        --coverage_file ${API}.profdata \
        --out ${NAME}.txt



    mkdir -p \
    $RESULT_DIR/$API/artifacts


    mv ${NAME}.txt \
    $RESULT_DIR/$API/


    mv ${API}.profraw \
    $RESULT_DIR/$API/artifacts/${NAME}.profraw


    mv ${API}.profdata \
    $RESULT_DIR/$API/artifacts/${NAME}.profdata


    cd ../..

done


cd $BASE_DIR

done


echo "ALL DONE"
