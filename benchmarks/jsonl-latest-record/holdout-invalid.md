# Contract review: holdout-invalid

Strict comparison keeps the first rather than last equal maximum version.

This is an attributed static review, independent of generated test rewards. Correctness is limited to the stated Contract.
{
  "argv": [
    "python",
    "/app/latest.py",
    "/tmp/input.jsonl",
    "/tmp/output.json"
  ],
  "stdin": "",
  "input_jsonl": [
    {
      "key": "a",
      "version": 2,
      "value": "new"
    },
    {
      "key": "a",
      "version": 2,
      "value": "last"
    }
  ],
  "expected": [
    {
      "key": "a",
      "version": 2,
      "value": "last"
    }
  ],
  "actual": [
    {
      "key": "a",
      "version": 2,
      "value": "new"
    }
  ]
}
