# 0) Make sure Xcode CLT is correct
xcode-select -p || xcode-select --install
sudo xcodebuild -license accept
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"

# 1) Build deps (Intel macs use /usr/local; Apple Silicon uses /opt/homebrew)
brew install openssl@3 bzip2 readline zlib xz sqlite tcl-tk

# 2) Environment so Python’s build system finds Homebrew stuff
BREW_PREFIX="$(brew --prefix)"
export CPPFLAGS="-I$(brew --prefix openssl@3)/include -I$(brew --prefix bzip2)/include -I$(brew --prefix readline)/include -I$(brew --prefix zlib)/include -I$(brew --prefix xz)/include -I$(brew --prefix sqlite)/include -I$(brew --prefix tcl-tk)/include"
export LDFLAGS="-L$(brew --prefix openssl@3)/lib -L$(brew --prefix bzip2)/lib -L$(brew --prefix readline)/lib -L$(brew --prefix zlib)/lib -L$(brew --prefix xz)/lib -L$(brew --prefix sqlite)/lib -L$(brew --prefix tcl-tk)/lib"
export PKG_CONFIG_PATH="$(brew --prefix openssl@3)/lib/pkgconfig:$(brew --prefix sqlite)/lib/pkgconfig:$(brew --prefix tcl-tk)/lib/pkgconfig"
# On macOS this helps tk/_tkinter + frameworks behave
export PYTHON_CONFIGURE_OPTS="--with-openssl=$(brew --prefix openssl@3) --enable-framework=${BREW_PREFIX}"

# 3) (Optional) clear partials from a stuck build
rm -rf ~/.pyenv/sources/*/Python-3.11.12 ~/.pyenv/versions/3.11.12

# 4) Verbose build (shows where it “hangs”)
PYENV_DEBUG=1 pyenv install -v 3.11.12

