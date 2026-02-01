# General Principles

You must always write code that (where relevant) fulfils all of the requirements of high quality code: - **Functionality (correctness)** : Works as expected and fulfills its intended purpose. - **Readability**: Is easy for humans to quickly comprehend (code is optimised for clarity). - **Documentation**: Clearly explains its purpose and usage. - **Standards Compliance**: Adheres to conventions and guidelines (e.g. PEP 8 for python code). - **Reusability**: Can be used in different contexts without modification. - **Maintainability**: Allows for modifications and extensions without introducing bugs. - **Robustness**: Handles errors and unexpected inputs effectively. - **Testability**: Can be easily verified for correctness. - **Efficiency**: Optimizes time and resource usage. - **Scalability**: Handles increased data loads or complexity without degradation. - **Security**: Protects against vulnerabilities and malicious inputs.

- Aim for high cohesion within modules and low coupling between them.
- Unless you are only providing a single argument and it is obvious what that argument is, always use named arguments when calling a function.
- Type annotate everything.
  - Make the type annotations as readable as possible (prioritise readability over comprehensiveness).
  - Don't use typing.Dict, typing.List, typing.Tuple etc. (you can use the base types dict, list, tuple etc. in type annotations since python 3.9).
  - After working on a piece of code, use `uv run ty check` to check that your type annotations are correct (you may need to install `ty` using `uv add --dev ty`)
- All modules, classes and functions must have google-style docstrings.
- Use assert statements frequently as lightweight validation of the expected state of the system.
  - Always include a short assert message.
- Aim for high cohesion within modules and low coupling between them.
- Unless you are only providing a single argument and it is obvious what that argument is, always use named arguments when calling a function.
- Very long `.py` scripts are a code smell. Over 500 lines is a warning, but generally still ok if there is a good reason. Python scripts over 1000 lines require a strong justification. Obviously, one expects HTML, template files, data files like CSV etc. to be very long.
- Code should not be platform-specific e.g. filepaths should use `Path(...)` from `pathlib` not windows path strings.

# Documentation

- All codebases should have a README.md file at the project root. It must be a brief but information dense document (optimised for human-readability) containing important context for understanding the application, intended to provide new developers with sufficient information to begin contributing to the codebase. It should include:
  - The name of the application
  - A high-level description of the primary goal(s) of the application
  - Instructions on how to setup and run the application (and test suite).
  - An explanation of the layout of the codebase
- Comments should be used sparingly. As far as possible, code should be self-documenting. Here are some general principles which often help:
  - Descriptive naming.
  - Complex logic broken down into well-named single-responsibility chunks (clean abstractions).
  - Use named constants.
  - No magic numbers (use named constants instead).

# Software Testing

- I don't believe in 100% test coverage, but please identify parts of the code which would be made more robust by adding tests and raise these with me.
- The test suite is going to consist of hundreds of tests, so ensure that no individual unit test takes more than 1 second to run.

# Error Handling

- Exceptions are an important signal and should not be thoughtlessly suppressed.
- Unexpected program behaviour must raise an exception (don't try to catch developer mistakes with error-handling code).
- A bare try/except may only be used at the topmost end-user-facing level of the application (if at all). All other exceptions must bubble up.

# User Inputs

- User inputs should always be assumed to be malicious.
