import { fileUrl } from "../api";
import type { Session } from "../types";
import { Kbd } from "./common";

export function PhotoPanel(props: {
  session: Session | null;
  query: string;
  onQuery: (q: string) => void;
  onNew: () => void;
}) {
  const s = props.session;
  const c = s?.photo.credit;
  return (
    <div className="photo-col">
      <div className="photo">
        {s ? (
          <img src={fileUrl("speaking", s.id, "photo.jpg")} alt={c?.alt ?? ""} />
        ) : (
          <div className="empty">
            <div>
              <p>写真がまだありません</p>
              <button className="btn primary" onClick={props.onNew}>
                写真を表示 <Kbd>N</Kbd>
              </button>
            </div>
          </div>
        )}
        <div className="meta">
          {c?.name && (
            <span>
              Photo by{" "}
              <a href={c.profile} target="_blank" rel="noreferrer">
                {c.name}
              </a>{" "}
              on{" "}
              <a href={c.link} target="_blank" rel="noreferrer">
                {s!.photo.source === "picsum" ? "Picsum" : "Unsplash"}
              </a>
            </span>
          )}
          <input
            value={props.query}
            onChange={(e) => props.onQuery(e.target.value)}
            placeholder="テーマ（例: street, cafe, kitchen）"
            title="次の写真のキーワード（空欄でランダム）"
          />
        </div>
      </div>
    </div>
  );
}
