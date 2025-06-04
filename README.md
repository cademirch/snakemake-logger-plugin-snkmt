# Snakemake Logger Plugin: snkmt

**This plugin is still under development and thus may not be fully stable or feature-complete. Use it at your own discretion and report any issues or suggestions to the repository's issue tracker.**

## Introduction

This is the logging plugin for use with [snkmt](https://github.com/cademirch/snkmt), a monitoring tool for Snakemake workflows. Please refer to [snkmt's](https://github.com/cademirch/snkmt) documentation for more details.

## Usage
1. Install via pip: `pip install snakemake-logger-plugin-snkmt`
2. Run Snakemake with the `--logger snkmt` option to enable the snkmt logger. 

>Note: Regular Snakemake logs will continue to be written to stderr when using this plugin, so it may appear that the plugin is not doing anything. This behavior will change in future versions.

## Options
- `--logger-snkmt-db </path/to/sqlite.db>"` Where to write the snkmt DB.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
