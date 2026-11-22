
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const shortAddress = user?.address
    ? `${user.address.slice(0, 6)}...${user.address.slice(-4)}`
    : "";

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6 shadow-sm">

      {/* Project name */}
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold text-slate-900">
          C3 <span className="text-cyan-600">ZKP</span>
        </h1>

        <span className="hidden border-l border-slate-300 pl-3 text-sm text-slate-500 sm:block">
          Supply Chain Verification
        </span>
      </div>

      {/* Wallet information */}
      <div className="flex items-center gap-4">

        <div className="hidden text-right sm:block">
          <p className="text-sm font-semibold text-slate-800">
            {user?.roleName}
          </p>

          <p className="text-xs text-slate-500">
            {shortAddress}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-green-500"></span>
          <span className="hidden text-xs text-green-600 sm:block">
            Connected
          </span>
        </div>

        <button
          onClick={handleLogout}
          className="rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50"
        >
          Logout
        </button>

      </div>
    </header>
  );
}

export default Header;
