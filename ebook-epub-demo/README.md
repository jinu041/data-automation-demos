# Ebook formatting demo: reflowable EPUB for Kindle

A short fiction ebook set up the way a KDP author needs it, using a public-domain story: Edgar Allan Poe, "The Tell-Tale Heart" (1843).

- `out/the-tell-tale-heart-demo.epub`: reflowable EPUB 3. The text follows the reader's font size and font choice, the table of contents is clickable (nav + NCX), the title-page and closing-page artwork are images that scale to the screen, and a short "About This Edition" page shows how scene breaks are set.
- `out/cover-kindle.jpg`: separate Kindle cover, RGB JPEG, 1600 × 2560 px (KDP's 1:1.6 ratio).
- `art/`: the PNG artwork the book is built from. These stand in for the files an author would supply; they are plain type and shapes, not AI images.

## Checks

- EPUBCheck 5.1.0: `No errors or warnings detected. Messages: 0 fatals / 0 errors / 0 warnings / 0 infos`
- The story text comes from the Standard Ebooks transcription (released under CC0) and was compared with the source page by SHA-256: 18 paragraphs and 21 italic spans, identical.
- Not yet checked in Kindle Previewer.

## Scene breaks

A break is its own centred paragraph (`* * *`) with margins in em and `page-break-after: avoid`, and the next paragraph starts flush left. Because it is real text and not an empty line, it doesn't disappear when the reader changes the font size or when the break lands at the top of a screen. Body text has no fixed font size or font family.

## Rebuild

```
pip install pillow
python build_epub.py
java -jar epubcheck.jar out/the-tell-tale-heart-demo.epub
```

`build_epub.py` uses the Python standard library plus Pillow for the artwork, and Georgia from `C:\Windows\Fonts` when it is there.

Made with Claude (an AI tool). This is a demo, not a client book.
