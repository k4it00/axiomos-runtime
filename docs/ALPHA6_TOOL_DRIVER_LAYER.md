# Alpha 6 Tool Driver Layer

## Architecture

```text
Package
  ↓
ToolRequest
  ↓
PermissionKernel
  ↓
ToolRegistry
  ↓
ToolDriver
  ↓
ToolResult
  ↓
Receipt
```

## Drivers

- FilesystemDriver
- GitDriver
- ShellDriver

## Permission categories

```text
read_file
write_file
list_dir
git_read
git_write
shell_limited
shell_full
network
external_effect
```

## Principle

Models and tools are both drivers, but tools require stricter permissions because they can change the outside world.
