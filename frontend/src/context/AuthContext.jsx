
import {
  createContext,
  useContext,
  useState,
  useEffect,
} from "react";

// Import wallet connection and MetaMask signature authentication.
import {
  connectWallet,
  signInWithWallet,
} from "../services/wallet";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);

  const login = async () => {
    try {
      setLoading(true);

      // Connect MetaMask and identify the stakeholder.
      const walletData = await connectWallet();

      // Authenticate wallet ownership through the backend.
      const authData = await signInWithWallet(walletData);

      // Store the JWT for authenticated API requests.
      sessionStorage.setItem("access_token", authData.access_token);

      // Update React authentication state after backend verification.
      const authenticatedUser = {
        address: authData.wallet_address,
        chainId: walletData.chainId,
        role: authData.role,
        roleName: authData.role_name,
        provider: walletData.provider,
        signer: walletData.signer,
        token: authData.access_token,
      };

      setUser(authenticatedUser);

      return authenticatedUser;
    } catch (error) {
      // Remove any previous token when authentication fails.
      sessionStorage.removeItem("access_token");
      setUser(null);
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    // Remove the JWT and clear the authenticated user.
    sessionStorage.removeItem("access_token");
    setUser(null);
  };

  // Detect MetaMask account and network changes.
  useEffect(() => {
    if (!window.ethereum) return;

    const handleAccountsChanged = () => {
      // Require authentication again after an account change.
      sessionStorage.removeItem("access_token");
      setUser(null);
    };

    const handleChainChanged = () => {
      // Require authentication again after a network change.
      sessionStorage.removeItem("access_token");
      setUser(null);
    };

    window.ethereum.on("accountsChanged", handleAccountsChanged);
    window.ethereum.on("chainChanged", handleChainChanged);

    return () => {
      window.ethereum.removeListener(
        "accountsChanged",
        handleAccountsChanged
      );
      window.ethereum.removeListener(
        "chainChanged",
        handleChainChanged
      );
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        isAuthenticated: Boolean(user),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
};
