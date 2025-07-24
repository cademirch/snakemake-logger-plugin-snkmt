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

## Development

This project uses [pixi](https://pixi.sh/) for environment management.

### Setting up the development environment

1. Clone the repository:
   ```bash
   git clone https://github.com/cademirch/snakemake-logger-plugin-snkmt.git
   cd snakemake-logger-plugin-snkmt
   ```

2. Install dependencies using pixi:
   ```bash
   pixi install
   ```

3. Activate the development environment:
   ```bash
   pixi shell -e dev
   ```

### Available development tasks

Run these commands with `pixi run` (or just use the command directly if you're in a pixi shell):

- **Quality control**: `pixi run qc` - Runs formatting, linting, and type checking
- **Testing**: `pixi run test` - Runs pytest with coverage reporting
- **Demo**: `pixi run demo` - Runs a demonstration Snakemake workflow using the plugin
- **Individual QC tasks**:
  - `pixi run format` - Format code with ruff
  - `pixi run lint` - Lint code with ruff
  - `pixi run type-check` - Type check with mypy

### Testing the plugin

To test the plugin with a real Snakemake workflow, use the demo task:

```bash
pixi run demo
```

This will:
1. Run a simple Snakemake workflow in `tests/demo/` using the snkmt logger
2. Create a SQLite database at `tests/demo/snkmt.db` with the logged workflow data
3. Clean up the demo directory afterward

You can also run the demo manually without cleanup using:
```bash
pixi run snk_demo
```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
