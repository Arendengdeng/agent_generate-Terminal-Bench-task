# Contract review: feedback-invalid

Unconditionally keeps last row and discards a higher version.

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
      "version": 1,
      "value": "last"
    }
  ],
  "expected": [
    {
      "key": "a",
      "version": 2,
      "value": "new"
    }
  ],
  "actual": [
    {
      "key": "a",
      "version": 1,
      "value": "last"
    }
  ]
}
