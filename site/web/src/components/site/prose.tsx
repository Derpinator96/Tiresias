// Shared text blocks for the content pages.
export const H1 = ({ children }: { children: React.ReactNode }) => (
  <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">{children}</h1>
);
export const H2 = ({ children, id }: { children: React.ReactNode; id?: string }) => (
  <h2 id={id} className="mb-3 mt-12 text-xl font-semibold tracking-tight text-slate-900">{children}</h2>
);
export const Lead = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-4 max-w-3xl text-base leading-relaxed text-slate-700">{children}</p>
);
export const P = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-700">{children}</p>
);
export const Panel = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div className={`glass rounded-xl p-5 ${className}`}>{children}</div>
);
