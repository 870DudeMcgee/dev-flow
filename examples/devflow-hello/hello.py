def build_greeting(name: str = "Devflow") -> str:
    cleaned_name = name.strip() or "Devflow"
    return f"Hello, {cleaned_name}!"


def main() -> None:
    print(build_greeting())


if __name__ == "__main__":
    main()