# Contributing and Development

We welcome contributions! To contribute to this repository, please follow these steps:

## Code and Testing

- **Code Style and Structure:**

- **Pre-Commit Hooks:** Install pre-commit hooks in this repository using the `pre-commit install` command.

- **Readable Code Structure:** Structure your code in a readable manner. The main logic should be in the default rule function, with implementation details in helper functions. Avoid nested `if` statements and unnecessary `else` statements to maintain code clarity and simplicity.

- **Remove Debug Statements:** Remove any development debug statements from your files.

- **Automated Tests:** We aim for full test coverage, so **partial tests will not be accepted**. The tests should cover all typical usage scenarios as well as edge cases to ensure robustness.

- **Testing Tool:** It is recommended to run `pytest` frequently during development to ensure that all aspects of your code are functioning as expected.

## Documentation and Maintenance

- **Changelog:** `CHANGELOG.md` is generated automatically by `commitizen` from commit messages. No need to update `CHANGELOG.md` manually. Focus on informative and clear commit messages that end up in the release notes.

- **Documentation:** Regularly check and update the documentation to keep it current.

- **PR/MR Descriptions and Documentation:** When making contributions, clearly describe any changes or new features in both the PR (Pull Request on GitHub) or MR (Merge Request on GitLab) description and the project documentation. If you're modifying the output style, please include a thumbnail of the new style.

## Correctness and Datasheet/TRM Mismatches

The ESP GPIO Tool is a convenience tool to help users get started and validate common configurations. The **datasheet and TRM are the source of truth**.

If you are fixing a mismatch versus the official documentation:

- Include an authoritative reference (datasheet/TRM name + section/page, or a stable link).
- Describe **expected vs actual** behavior/output.
- Add a regression test when feasible, or include a minimal YAML config + expected diagnostics so it can be turned into a test later.

## Development and Local Testing

1. **Clone the Project**

- Clone the repository to your local machine using:

```sh
git clone <project_clone_url>
```

2. **Set Up Development Environment:**

- Create and activate a virtual environment:

  ```sh
  python -m venv venv && source ./venv/bin/activate
  ```

  or:

  ```sh
  virtualenv venv && source ./venv/bin/activate
  ```

- Install the project and development dependencies:
  ```sh
  pip install -e '.[dev]'
  ```

3. **Testing Your Changes:**

- Before submitting a pull request, ensure your changes pass all the tests. You can run the test suite with the following command:

  ```sh
  pytest
  ```

---

👏**Thank you for your contributions.**
