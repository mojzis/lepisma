---
kind: fixed
---

`Measurer.measure` returns an empty result when no document in the batch has prose, such as an empty file, a heading alone or a file that is only a code block. It used to raise a polars `SchemaError`.
