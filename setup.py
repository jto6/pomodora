from setuptools import setup, find_packages

setup(
    name="pomodora",
    version="0.1.0",
    description="Linux GUI Pomodoro Activity Tracker",
    author="Developer",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "tkinter",
    ],
    entry_points={
        "console_scripts": [
            "pomodora=main:main",
        ],
    },
)