# One known-bad sample per rule

<!-- R1 -->
We read the file and then we print it, we read the file and then we print it, and so we stop the run here now.

<!-- R2 -->
Check the pipeline configuration validation error handling code.

<!-- R3 -->
We leverage the cache.

<!-- R4 -->
The service performs validation of the input.

<!-- R5 -->
Every file that the old importer wrote to the shared folder during the nightly run last week has been deleted.

<!-- R6 -->
The cache keeps the last ten results. This allows faster lookups. Old results drop out first.

<!-- R7 -->
The importer reads each row and writes it to the table. Overall, the import is simple.

<!-- R8 -->
The cache — a plain dict — holds the parsed files (one for each path); nothing else is kept.

<!-- R9 -->
# A report, not a gate

The hook is an inventory, not a verdict. It lists findings rather than blocking the commit. The exit code isn't a judgment. It's a count.

<!-- R10 -->
The daemon speaks LSP to the type checker.

<!-- R11 -->
The seam between the two modules is narrow. Each seam has one owner. The verdict lands in the report.
