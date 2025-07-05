import importlib, sys

try:
    rust_mod = importlib.import_module("rust")
    # bring symbols into package namespace
    globals().update({name: getattr(rust_mod, name) for name in dir(rust_mod) if not name.startswith("__")})
except ImportError:
    # If the compiled module is not available, provide a fallback or error message
    print("Warning: Rust native module 'rust' not compiled. Run 'maturin develop' in jesse/rust.")
    # You could also raise an exception or provide Python fallbacks here
    pass