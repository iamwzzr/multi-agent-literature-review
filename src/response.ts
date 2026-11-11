import type { ReviewSection } from './demo'

export function visibleParagraph(text: string) {
  return text.replace(/\[(?:\[\d*\]?)?$/u, '').replace(/[\uD800-\uDBFF]$/u, '')
}

export function reportLength(sections: ReviewSection[]) {
  return sections.reduce((length, { heading, paragraphs }) => (
    length + heading.length + paragraphs.reduce((total, paragraph) => total + paragraph.length, 0)
  ), 0)
}

export function revealSections(sections: ReviewSection[], length: number): ReviewSection[] {
  const visible: ReviewSection[] = []
  let remaining = length

  for (const section of sections) {
    if (remaining < section.heading.length) break
    remaining -= section.heading.length
    const paragraphs: string[] = []

    for (const paragraph of section.paragraphs) {
      if (remaining <= 0) break
      const end = Math.min(remaining, paragraph.length)
      const text = end === paragraph.length
        ? paragraph
        : visibleParagraph(paragraph.slice(0, end))
      if (text) paragraphs.push(text)
      remaining -= end
    }

    visible.push({ ...section, paragraphs })
  }

  return visible
}
