#!/bin/bash
set -o errexit -o nounset -o pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install build-essential software-properties-common -y
add-apt-repository ppa:ubuntu-toolchain-r/test -y
apt-get update -y
apt-get install build-essential software-properties-common -y
apt-get update

apt-get install gcc-11 g++-11 -y
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 60 --slave /usr/bin/g++ g++ /usr/bin/g++-11
update-alternatives --set gcc /usr/bin/gcc-11

apt-get install git wget -y
apt-get install unzip cmake ninja-build fontconfig libfontconfig1-dev libglu1-mesa-dev curl zip pkg-config -y

apt-get install python3.9 -y
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 100
