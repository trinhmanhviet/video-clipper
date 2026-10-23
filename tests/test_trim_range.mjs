import test from 'node:test';
import assert from 'node:assert/strict';
import { clampTrimHandle } from '../static/trim-range.mjs';

test('start handle stops one source frame before end', () => {
  assert.equal(clampTrimHandle('start', 8, 5, 10, 30), 5 - 1 / 30);
});
test('end handle cannot cross start', () => {
  assert.equal(clampTrimHandle('end', 1, 4, 10, 24), 4 + 1 / 24);
});
test('dragging clamps to video boundaries', () => {
  assert.equal(clampTrimHandle('start', -10, 5, 10, 30), 0);
  assert.equal(clampTrimHandle('end', 50, 4, 10, 30), 10);
});
test('short clips and invalid pointer values remain valid', () => {
  assert.equal(clampTrimHandle('start', 1, .01, .01, 30), 0);
  assert.equal(clampTrimHandle('end', NaN, 0, .01, 30), .01);
});
test('normal drag preserves subsecond precision', () => {
  assert.equal(clampTrimHandle('start', 1.237, 5, 10, 30), 1.237);
  assert.equal(clampTrimHandle('end', 7.819, 1, 10, 30), 7.819);
});
