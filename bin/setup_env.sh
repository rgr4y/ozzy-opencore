# Make sure Xcode CLT is good
xcode-select -p || xcode-select --install
sudo xcodebuild -license accept
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"

# Update Homebrew + pyenv stack
brew update
brew upgrade pyenv python-build

# (If you installed pyenv via git in $HOME instead of brew, also do:)
# git -C ~/.pyenv pull
# git -C ~/.pyenv/plugins/python-build pull

# Build deps so the linker stops “hunting”
brew install openssl@3 bzip2 readline zlib xz sqlite tcl-tk

# Reinstall, verbosely (you’ll see where it spends time)
PYENV_DEBUG=1 pyenv install -v 3.11.12