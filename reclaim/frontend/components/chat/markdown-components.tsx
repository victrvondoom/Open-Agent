/** Shared ReactMarkdown component overrides -- styled with EB Garamond / Anthropic Serif
 * for literary editorial authority, paired with Figtree and JetBrains Mono for data tokens.
 * Used by the AI Assistant chat, Appeals document viewer, and Case Reports. */
export const markdownComponents = {
  h1: (props: any) => (
    <h3 className="mb-2 mt-4 font-serif text-xl font-bold tracking-tight text-[#1c1917] first:mt-0" {...props} />
  ),
  h2: (props: any) => (
    <h4 className="mb-1.5 mt-3.5 font-serif text-lg font-bold tracking-tight text-[#1c1917] first:mt-0" {...props} />
  ),
  h3: (props: any) => (
    <h5 className="mb-1 mt-3 font-serif text-base font-bold text-amber-900 first:mt-0" {...props} />
  ),
  p: (props: any) => (
    <p className="mb-2.5 font-serif text-[15px] leading-[1.68] text-[#292524] last:mb-0" {...props} />
  ),
  strong: (props: any) => (
    <strong className="font-bold text-[#1c1917]" {...props} />
  ),
  em: (props: any) => (
    <em className="font-serif italic text-stone-800" {...props} />
  ),
  blockquote: (props: any) => (
    <blockquote className="my-3 border-l-4 border-[#231f1d] bg-amber-50/60 py-2 pl-3.5 pr-3 font-serif italic text-[14px] leading-relaxed text-stone-800 rounded-r" {...props} />
  ),
  ul: (props: any) => (
    <ul className="mb-2.5 ml-4 list-disc space-y-1 font-serif text-[14.5px] leading-relaxed text-[#292524]" {...props} />
  ),
  ol: (props: any) => (
    <ol className="mb-2.5 ml-4 list-decimal space-y-1 font-serif text-[14.5px] leading-relaxed text-[#292524]" {...props} />
  ),
  li: (props: any) => <li className="pl-0.5" {...props} />,
  code: (props: any) => (
    <code className="rounded border border-[#231f1d] bg-[#fbf8f0] px-1.5 py-0.5 font-mono text-xs font-bold text-amber-950" {...props} />
  ),
  a: (props: any) => (
    <a className="font-serif font-bold text-amber-800 underline decoration-amber-600/50 hover:text-amber-950" target="_blank" rel="noreferrer" {...props} />
  ),
};

