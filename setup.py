import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="dashborg-python-sdk",
    version="0.3.0.dev1",
    author="Michael Sawka",
    author_email="mike@dashborg.net",
    description="Dashborg Python SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sawka/dashborg-python-sdk",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'aiofiles',
        'cffi',
        'cryptography',
        'ecdsa',
        'grpcio',
        'grpcio-tools',
        'protobuf',
        'pycparser',
        'six',
    ],
    python_requires='>=3.6',
)
