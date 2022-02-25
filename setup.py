from setuptools import find_packages, setup

setup(
    name="copybot",
    version="0.1",
    py_modules=["copybot"],
    packages=["."] + find_packages(),
    entry_points={"console_scripts": ("copybot = main:cli")},
)
