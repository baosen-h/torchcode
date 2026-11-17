# Attribution and provenance

This repository builds on [duoan/TorchCode](https://github.com/duoan/TorchCode).
The upstream PyTorch problems, reference solutions, notebook integration,
judge, and original web interface remain credited to An, Duo
(duoan) and the upstream contributors.

The starting upstream revision for this version is
[`e3c8782a4be4f7cdb4de871ec739f66370968a77`](https://github.com/duoan/TorchCode/commit/e3c8782a4be4f7cdb4de871ec739f66370968a77).
The original README is preserved in [README.upstream.md](README.upstream.md).

At that revision, the upstream README identifies MIT as the license, and
`pyproject.toml`, `labextension/package.json`, and `labextension/pyproject.toml`
also declare MIT. The upstream tree does not include a standalone `LICENSE`
file. This repository supplies the standard MIT text and explicit attribution
in [LICENSE](LICENSE), based on those upstream declarations; that file is not
represented as a verbatim upstream license file.

Modifications maintained by baosen-h add the personal problem library,
editable categories, personal notes and drafts, custom tests and execution,
Conda environment management, Windows launcher, persistence, backups, and
the bilingual interface and documentation for these features. These modifications are also provided
under MIT. This is an independently maintained derivative of TorchCode.

Third-party libraries retain their respective licenses. They are installed
through Python and npm; their source distributions are not vendored here.
Documentation screenshots use demonstration questions and illustrative
environment paths, not a user's private library or local machine details.

## Repository relationship and contributor statistics

The GitHub repository `baosen-h/torchcode` is a personal adaptation shared for
others to use, independently maintained and not currently marked as a GitHub
fork. Its default branch begins with a fresh snapshot rather than inherited
upstream commits. The GitHub contributor statistic describes this repository's
commit history, not authorship of all the included source. This change to the
Git history does not remove or replace upstream copyright and license notices.
The upstream revision linked above identifies the source of the retained work.

The current English documentation is [README.md](README.md), with a Chinese
translation in [README.zh-CN.md](README.zh-CN.md). Each uses screenshots of the
corresponding interface language. The upstream README is an unchanged
historical archive of the original PyTorch-focused project.
