# Snakemake Logger Plugin: snkmt

**This plugin is still under development and thus may not be fully stable or feature-complete. Use it at your own discretion and report any issues or suggestions to the repository's issue tracker.**

## Introduction

The **Snakemake Logger Plugin: snkmt** is a logger plugin for Snakemake that writes workflow execution logs to a SQLite database. This plugin enables detailed tracking of workflows, rules, jobs, and associated files, providing a structured and queryable format for analyzing workflow execution. This enables visual monitoring of workflows using [snkmt](https://github.com/cademirch/snkmt). 

## Usage
1. Install via pip: `pip install snakemake-logger-plugin-snkmt`
2. Run Snakemake with the `--logger snkmt` option to enable the snkmt logger. 

## Options
TODO

## Design
1. **Log Handler**:
   - The `sqliteLogHandler` class processes log records and delegates them to event handlers.
   - Manages database sessions and ensures transactional consistency.

2. **Event Handlers**:
   - Specialized handlers process specific log events (e.g., workflow start, job info, errors).
   - Handlers parse log records and update the database models accordingly.

3. **Database Models**:
   - SQLAlchemy models represent key entities such as workflows, rules, jobs, files, and errors.
   - Models capture attributes and relationships for comprehensive logging. Model definitions are maintained in the[snkmt repo](https://github.com/cademirch/snkmt).

## Development

TODO

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository and create a new branch.
2. Make your changes and ensure all tests pass.
3. Submit a pull request with a detailed description of your changes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
