# 1) Make sure Xcode CLT is good
xcode-select -p || xcode-select --install
sudo xcodebuild -license accept
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"

# 2) Update Homebrew + pyenv stack
brew update
brew upgrade pyenv python-build

# (If you installed pyenv via git in $HOME instead of brew, also do:)
# git -C ~/.pyenv pull
# git -C ~/.pyenv/plugins/python-build pull

# 3) Build deps so the linker stops “hunting”
brew install openssl@3 bzip2 readline zlib xz sqlite tcl-tk

# 4) Environment hints so Python’s build can find Homebrew libs
export CPPFLAGS="-I$(brew --prefix openssl@3)/include -I$(brew --prefix bzip2)/include -I$(brew --prefix readline)/include -I$(brew --prefix zlib)/include -I$(brew --prefix xz)/include -I$(brew --prefix sqlite)/include -I$(brew --prefix tcl-tk)/include"
export LDFLAGS="-L$(brew --prefix openssl@3)/lib -L$(brew --prefix bzip2)/lib -L$(brew --prefix readline)/lib -L$(brew --prefix zlib)/lib -L$(brew --prefix xz)/lib -L$(brew --prefix sqlite)/lib -L$(brew --prefix tcl-tk)/lib"
export PKG_CONFIG_PATH="$(brew --prefix openssl@3)/lib/pkgconfig:$(brew --prefix sqlite)/lib/pkgconfig:$(brew --prefix tcl-tk)/lib/pkgconfig"

# Optional, but helps on macOS: build a frameworked Python
export PYTHON_CONFIGURE_OPTS="--with-openssl=$(brew --prefix openssl@3) --enable-framework=$(brew --prefix)"

# 5) Nuke the failed attempt so the installer doesn’t reuse it
rm -rf ~/.pyenv/sources/*/Python-3.11.12 ~/.pyenv/versions/3.11.12 ~/.pyenv/cache/*

# 6) Reinstall, verbosely (you’ll see where it spends time)
PYENV_DEBUG=1 pyenv install 3.11.12