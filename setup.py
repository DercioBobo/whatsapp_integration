"""
WhatsApp Notifications for ERPNext
A flexible WhatsApp notification service using Evolution API
Compatible with ERPNext v13, v14, and v15
"""
from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

with open("README.md") as f:
    long_description = f.read()

setup(
    name="whatsapp_notifications",
    version="1.0.0",
    description="WhatsApp Notifications for ERPNext using Evolution API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Bobo",
    author_email="bobo@entretech.co.mz",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Frappe",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Communications :: Chat",
    ],
)
