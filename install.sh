set -e

# update system
sudo apt update -y && sudo apt full-upgrade -y

# create folder
mkdir launchpad
cd launchpad

# install dependencies
sudo apt install -y git python3-pip python3-pygame python3-setuptools python3-dotenv

# install launchpad package
git clone https://github.com/FMMT666/launchpad.py.git
cd launchpad.py
sudo python setup.py install

# return
cd ..