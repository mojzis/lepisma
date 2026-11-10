---
title: DataSync
status: stable
---

# DataSync: A Comprehensive and Robust Data Synchronization Solution

Welcome to DataSync, a comprehensive solution that leverages cutting-edge technology in order to provide seamless synchronization of data across a wide variety of heterogeneous storage backends, ensuring that your datasets remain consistent, reliable, and up to date at all times.

## Overview

DataSync is designed to facilitate the movement of records between systems. It is important to note that the tool performs validation of every record before it is written, and it provides support for a number of different source types. The synchronization engine is responsible for the management of the scheduling, the retry logic, and the conflict resolution strategy, all of which can be tuned by the operator.

Our robust architecture makes use of a worker pool pattern. Our design allows for horizontal scaling. Our team has made a decision to prioritize correctness over raw throughput (although throughput is still quite good).

## Installation

To get started, utilize the following command in order to install the package:

```bash
pip install datasync==2.4.1 --extra-index-url https://packages.example.com/simple --trusted-host packages.example.com --no-cache-dir --upgrade --utilize-wheels
```

You can then verify the installation by running `datasync --version`, which should print the version number of the installed release.

## Configuration

The following options are supported:

- `max_retries`
- `batch_size`
- `source_url`
- `conflict_policy`

| Option | Default | Description |
|--------|---------|-------------|
| `max_retries` | 5 | Number of attempts before a record is dead-lettered |
| `batch_size` | 500 | Records per transaction |
| `conflict_policy` | `newest` | How to resolve conflicting writes |

It is important to note that the default values were chosen after comprehensive benchmarking of the pipeline configuration validation error handling subsystem, and that changing them without a thorough understanding of the downstream storage characteristics may lead to degraded performance.

## Usage

Synchronization jobs are defined in a YAML file, the file is parsed by the loader, the parsed configuration is validated by the schema checker, and the validated job is then handed to the scheduler, which is responsible for the execution of the job at the appropriate time according to the cron expression that was specified by the user.

For more details, see the [full documentation](https://docs.example.com/datasync/guides/advanced/configuration/synchronization-jobs/reference/index.html).

## Contributing

Contributions are welcome! Please ensure that all tests pass before you submit a pull request, and ensure that your commit messages are descriptive.

## In Summary

Overall, DataSync is a powerful, flexible, and seamless tool that streamlines the synchronization process. Whether you are a seasoned engineer or a newcomer, DataSync will facilitate your data workflows and ensure a delightful experience.
