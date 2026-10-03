// Shared blocks for the content pages: short headings, one-line leads, a page frame.
export const Page = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-auto w-full max-w-5xl px-4 py-8 lg:px-8">{children}</div>
);
export const H1 = ({ children }: { children: React.ReactNode }) => (
  <h1 className="max-w-3xl text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">{children}</h1>
);
export const H2 = ({ children }: { children: React.ReactNode }) => (
  <h2 className="mb-3 mt-10 text-lg font-semibold tracking-tight text-slate-900">{children}</h2>
);
export const Lead = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-2 max-w-2xl text-base text-slate-600">{children}</p>
);
export const P = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-700">{children}</p>
);
