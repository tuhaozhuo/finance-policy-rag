import re


class TextCleaner:
    def clean(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in text.split("\n")]

        cleaned: list[str] = []
        prev = ""
        for line in lines:
            if not line:
                if prev:
                    cleaned.append("")
                prev = ""
                continue
            if line == prev:
                continue
            cleaned.append(line)
            prev = line

        merged = "\n".join(cleaned)
        merged = re.sub(r"\n{3,}", "\n\n", merged)
        merged = re.sub(r"[ \t]{2,}", " ", merged)
        return merged.strip()
