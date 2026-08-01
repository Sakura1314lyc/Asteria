import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="not-found">
      <span>404 / LOST NODE</span>
      <h1>这条研究路径不存在。</h1>
      <p>可能是项目已移动，或链接中的运行 ID 不完整。</p>
      <Link className="button button--primary button--medium" to="/">
        <ArrowLeft size={15} /> 返回工作台
      </Link>
    </div>
  );
}
