# NOTICE

Attribution and trademark notices for the Software Factory skill pack.

## License

Copyright (c) 2026 sbeeredd04 and Software Factory contributors.

Content authored in this repository ("factory-owned content") is licensed under the MIT
license; see [LICENSE](LICENSE). This notice does not modify that license.

## Referenced third-party tooling

Software Factory composes with third-party tooling, which is always obtained through its own
distribution channel. The pack does not vendor those tools; the copied schema
and code-of-conduct materials are identified separately below:

- **BMad Method v6** provides planning. It is installed by its own pinned npm installer
  (`npx bmad-method@6.12.0 install ...`) into your project, under its own license and terms.
  This repository ships no BMad files. Compatibility statement: **"Works with BMad Method v6."**
- **Claude Code**, **Cursor**, and **Codex** are the supported hosts. Software Factory generates
  host-formatted projections for them; it ships none of their software.
- Review-bot integrations (Greptile, CodeRabbit, Bugbot, GitHub Copilot code review) are
  optional and disabled by default. The pack only generates configuration files at your
  request.

## Copied schema material

`schemas/plugins/portable.schema.json` is an unchanged copy of the Agent Plugins
1.0.0 manifest schema from the Agent Plugins project. Source and license were
verified at upstream revision `ff8ab5e392cc87bd88d87c060815a87490e51003`:

- [Original schema](https://github.com/agentplugins/agent-plugins-spec/blob/ff8ab5e392cc87bd88d87c060815a87490e51003/schemas/1.0.0/plugin.schema.json).
- [Upstream license mapping](https://github.com/agentplugins/agent-plugins-spec/blob/ff8ab5e392cc87bd88d87c060815a87490e51003/LICENSE.md)
  licenses schemas under Apache License 2.0, separately from documentation.
- The complete upstream Apache License 2.0 text accompanies the schema at
  `schemas/plugins/LICENSE-APACHE-2.0.txt`; it also remains available
  [upstream](https://github.com/agentplugins/agent-plugins-spec/blob/ff8ab5e392cc87bd88d87c060815a87490e51003/LICENSES/Apache-2.0.txt).

This third-party schema retains its Apache-2.0 license; the MIT license for
factory-authored content does not replace it. Native plugin bundles contain
factory projections and this notice, but do not contain the validation schema.

## Software-design sources

The `sf-design`, `sf-smell-audit`, `sf-refactor`, and `sf-patterns` skills distill widely
published software-design knowledge. We learned from, and recommend, these sources. Their prose
is theirs; it is not reproduced in this repository:

- Refactoring.Guru (https://refactoring.guru) - smell and refactoring catalogs.
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed.
  (Addison-Wesley) - the refactoring discipline.
- Erich Gamma, Richard Helm, Ralph Johnson, and John Vlissides, *Design Patterns: Elements of
  Reusable Object-Oriented Software* ("Gang of Four") - pattern judgment.

The code of conduct in this repository is the Contributor Covenant, version 2.1
(https://www.contributor-covenant.org/version/2/1/code_of_conduct.html), used under the terms
of its license (CC BY 4.0).

## Trademarks and non-affiliation

Claude Code is a product of Anthropic PBC; Cursor is a product of Anysphere, Inc.; Codex is a
product of OpenAI; GitHub and Copilot are products of GitHub, Inc.; BMad Method is a project of
its own maintainers. **Software Factory is not affiliated with, endorsed by, or sponsored by
Anthropic, Anysphere, OpenAI, GitHub, or the BMad Method maintainers.** All product names and
trademarks are the property of their respective owners; they are used here only to state
compatibility, under nominative fair use. This project is not a BMad Method product and its
name contains no BMad trademark.
