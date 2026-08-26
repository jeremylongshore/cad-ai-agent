// commitlint — enforces conventional commit messages + epic/bead trailers (CLAUDE.md)
// Invoked via pre-commit `commit-msg` stage hook.
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always', ['feat', 'fix', 'docs', 'style', 'refactor', 'test', 'chore', 'perf', 'ci', 'build', 'revert']],
    'subject-case': [0],
    'header-max-length': [2, 'always', 100],
  },
};
