# Vendored native Lighter signer binaries (Go -> C, loaded via ctypes by the jesse-live
# Lighter live driver). Kept here in the pure-Python `jesse` package so they ship as plain
# package data — jesse builds a pure-Python wheel with no auditwheel/delocate repair step,
# unlike jesse-live's compiled cibuildwheel build which rejects these prebuilt binaries.
# Same pattern as Apex's omni_files. This __init__.py makes the dir a package so setup.py's
# package_data (*.so/*.dylib/*.dll) bundles the binaries into the wheel.
