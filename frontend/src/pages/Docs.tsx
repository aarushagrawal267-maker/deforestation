import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { marked } from "marked";
import { NavLink, useParams } from "react-router-dom";
import { api } from "../api/client";
import { PageHeader, Spinner } from "../components/ui";

interface DocMeta {
  slug: string;
  title: string;
}

export default function DocsPage() {
  const { doc } = useParams();
  const { data: list } = useQuery({ queryKey: ["docs"], queryFn: () => api.get<DocMeta[]>("/docs") });
  const slug = doc ?? list?.[0]?.slug;
  const { data: md, isLoading } = useQuery({
    queryKey: ["doc", slug],
    queryFn: () => api.get<{ slug: string; markdown: string }>(`/docs/${slug}`),
    enabled: !!slug,
  });
  return (
    <div>
      <PageHeader
        eyebrow="Research & documentation"
        title="Methodology, data and limitations"
        description="Rendered from the repository's docs/ folder, which is the single source of truth for reproducibility."
      />
      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="space-y-0.5 lg:sticky lg:top-4 lg:self-start" aria-label="Documentation">
          {list?.map((d) => (
            <NavLink
              key={d.slug}
              to={`/docs/${d.slug}`}
              className={({ isActive }) =>
                clsx(
                  "block rounded-lg px-3 py-1.5 text-[13px]",
                  isActive || (!doc && d.slug === slug) ? "bg-accent-soft text-ink" : "text-muted hover:bg-raised hover:text-ink",
                )
              }
            >
              {d.title}
            </NavLink>
          ))}
        </nav>
        <article className="prose-sylva max-w-3xl rounded-xl border border-line bg-surface px-8 py-7">
          {isLoading || !md ? <Spinner /> : <div dangerouslySetInnerHTML={{ __html: marked.parse(md.markdown, { async: false }) as string }} />}
        </article>
      </div>
    </div>
  );
}
