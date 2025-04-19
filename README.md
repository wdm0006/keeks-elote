# Keeks-Elote

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
<!-- Add badges for build status, coverage, etc. if available -->

A Python library integrating the [`elote`](https://elote.mcginniscommawill.com) rating system library and the [`keeks`](https://keeks.mcginniscommawill.com) bankroll management library to facilitate backtesting and evaluation of combined ranking and betting strategies.

## Purpose

The primary goal of `keeks-elote` is to provide a framework for simulating and analyzing the performance of different rating algorithms (like Elo, Glicko, etc.) when coupled with various bankroll management strategies (like Kelly Criterion, fixed betting, etc.). This allows users to explore how prediction accuracy from rating systems translates into profitability under different staking plans in competitive scenarios (e.g., sports betting, gaming).

## Why is this interesting? (Features)

*   **Integration:** Seamlessly combines rating generation (`elote`) with betting strategy simulation (`keeks`).
*   **Backtesting Framework:** Provides tools to run historical simulations on outcome data.
*   **Flexibility:** Supports multiple rating systems and bankroll management techniques available in the underlying libraries.
*   **Evaluation:** Enables analysis of strategy performance based on metrics like profit/loss, ROI, etc.
*   **Extensibility:** Designed to be potentially extended with custom rating models or betting strategies.

## Installation

You can install `keeks-elote` directly from the repo, soon we will publish it to PyPI.

```bash
git clone https://github.com/wmcginnis/keeks-elote.git
cd keeks-elote
pip install -e .
```

For development, clone the repository and install in editable mode with development dependencies:

```bash
git clone https://github.com/wmcginnis/keeks-elote.git
cd keeks-elote
pip install -e .[dev]
```

## How to Use It

The core idea is to use `elote` to generate ratings and predictions based on historical match/game data and then use `keeks` to simulate betting on those predictions according to a chosen bankroll strategy.

TODO: real example.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (if one exists, otherwise state MIT).
