# Contributing to Azone

Thank you for your interest in contributing to Azone!

## How to Contribute

1. Fork the repository
2. Create a feature branch: git checkout -b my-feature
3. Commit your changes: git commit -am "Add feature"
4. Push to the branch: git push origin my-feature
5. Submit a Pull Request

## Development Setup

```bash
git clone https://github.com/tianzizhiming-svg/azone.git
cd azone
pip install fastapi uvicorn httpx
uvicorn main:app --host 0.0.0.0 --port 8002
```

## API Endpoints

- GET /.well-known/azone - Protocol metadata
- POST /azone/v1/register - Register agent
- GET /azone/v1/discover - Discover agents
- GET /azone/v1/agents/{azone_id} - Agent details

## Code Style

- Python 3.10+
- FastAPI framework
- Type hints required
- UTF-8 encoding

## Reporting Issues

Please open a GitHub Issue with:
- Description of the problem
- Steps to reproduce
- Expected vs actual behavior

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
