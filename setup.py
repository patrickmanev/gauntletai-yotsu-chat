from setuptools import setup, find_packages

setup(
    name="yotsu_chat",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "aiosqlite",
        "python-jose[cryptography]",
        "passlib[bcrypt]",
        "python-multipart",
        "pyotp",
        "aiofiles",
        "python-magic-bin; platform_system == 'Windows'",
        "python-magic; platform_system != 'Windows'",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-asyncio",
            "httpx",
            "asgi-lifespan",
        ]
    }
) 