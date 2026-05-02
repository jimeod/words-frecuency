def split_text(text: str, num_chunks: int) -> list[str]:

    words = text.split()
    if not words:
        return [""] * num_chunks

    chunk_size = max(1, len(words) // num_chunks)
    chunks = []

    for i in range(num_chunks):
        start = i * chunk_size
        if i == num_chunks - 1:
            end = len(words)
        else:
            end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)


    chunks = [c for c in chunks if c.strip()]
    return chunks
