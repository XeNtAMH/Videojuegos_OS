import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import OwnerDashboard from "./OwnerDashboard.jsx";
import ConfirmationDialog, { useConfirmationDialog } from "./ConfirmationDialog.jsx";

const CUP = new Intl.NumberFormat("es-CU", { maximumFractionDigits: 0 });
const money = (value) => `${CUP.format(value)} CUP`;
const emptyCart = {};

function viewForPath(pathname) {
  if (pathname === "/" || pathname === "/home") return "shop";
  if (pathname === "/login" || pathname === "/register") return "account";
  if (pathname === "/cart") return "cart";
  if (pathname === "/orders") return "orders";
  if (pathname === "/owner") return "owner";
  if (/^\/product\/\d+\/?$/.test(pathname)) return "product";
  return "shop";
}

function productIdForPath(pathname) {
  const match = pathname.match(/^\/product\/(\d+)\/?$/);
  return match ? Number(match[1]) : null;
}

function App() {
  const [settings, setSettings] = useState(null);
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("store-cart") || "{}");
    } catch {
      return {};
    }
  });
  const [token, setToken] = useState(() => sessionStorage.getItem("store-token"));
  const [currentUser, setCurrentUser] = useState(null);
  const [orders, setOrders] = useState([]);
  const [view, setCurrentView] = useState(() => viewForPath(window.location.pathname));
  const [selectedProductId, setSelectedProductId] = useState(() =>
    productIdForPath(window.location.pathname),
  );
  const [category, setCategory] = useState("Todos");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [recentlyAddedId, setRecentlyAddedId] = useState(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [proofFiles, setProofFiles] = useState({});
  const [proofPreview, setProofPreview] = useState("");
  const [selectedPayment, setSelectedPayment] = useState("cash");
  const [showRegisterFields, setShowRegisterFields] = useState(
    () => window.location.pathname === "/register",
  );
  const emailInput = useRef(null);
  const proofInput = useRef(null);
  const confirmation = useConfirmationDialog();

  useEffect(() => {
    if (!proofPreview) return undefined;
    return () => URL.revokeObjectURL(proofPreview);
  }, [proofPreview]);

  function setView(destination, productId = null) {
    let nextView = destination;
    let nextPath;
    if (destination === "register") {
      nextView = "account";
      nextPath = "/register";
      setShowRegisterFields(true);
    } else if (destination === "login" || destination === "account") {
      nextView = "account";
      nextPath = "/login";
      setShowRegisterFields(false);
    } else {
      nextPath = {
        shop: "/home",
        cart: "/cart",
        orders: "/orders",
        owner: "/owner",
        product: productId ? `/product/${productId}` : null,
      }[destination];
    }

    if ((nextView === "cart" || nextView === "orders") && !token) {
      nextView = "account";
      nextPath = "/login";
      setShowRegisterFields(false);
      setNotice("Inicia sesión con una cuenta verificada para continuar.");
      setError("");
    }
    if (!nextPath) return;
    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, "", nextPath);
    }
    if (destination === "product") {
      setSelectedProductId(productId);
      setSelectedImageIndex(0);
    }
    if (destination === "shop" || destination === "cart" || destination === "orders" || destination === "product" || destination === "owner") {
      setSelectedProductId(null);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    if (destination === "product") {
      setSelectedProductId(productId);
    }
    setCurrentView(nextView);
  }

  const categories = useMemo(
    () => ["Todos", ...new Set(products.map((product) => product.category))],
    [products],
  );
  const visibleProducts =
    category === "Todos"
      ? products
      : products.filter((product) => product.category === category);
  const cartProducts = Object.entries(cart)
    .map(([id, quantity]) => {
      const product = products.find((item) => item.id === Number(id));
      return product ? { ...product, quantity } : null;
    })
    .filter(Boolean);
  const cartCount = cartProducts.reduce((sum, item) => sum + item.quantity, 0);
  const cartTotal = cartProducts.reduce(
    (sum, item) => sum + item.price_cup * item.quantity,
    0,
  );
  const zelleAvailable = cartProducts.some((item) => item.zelle_eligible);
  const selectedProduct = products.find(
    (product) => product.id === selectedProductId,
  );
  const paymentInstructions = {
    bpa: settings?.bpa_instructions,
    mobile: settings?.mobile_balance_instructions,
    zelle: settings?.zelle_instructions,
  }[selectedPayment];

  async function loadProducts() {
    const result = await api("/products/");
    setProducts(result);
  }

  async function loadOrders(activeToken = token) {
    if (!activeToken) return;
    const result = await api("/orders/", { token: activeToken });
    setOrders(result);
  }

  useEffect(() => {
    Promise.all([api("/store-settings/"), loadProducts()])
      .then(([store]) => setSettings(store))
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    localStorage.setItem("store-cart", JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    if (!notice && !error) return undefined;
    const timeout = window.setTimeout(() => {
      setNotice("");
      setError("");
    }, 5000);
    return () => window.clearTimeout(timeout);
  }, [notice, error]);

  useEffect(() => {
    if (recentlyAddedId === null) return undefined;
    const timeout = window.setTimeout(() => setRecentlyAddedId(null), 1500);
    return () => window.clearTimeout(timeout);
  }, [recentlyAddedId]);

  useEffect(() => {
    if (!token) setCart(emptyCart);
  }, [token, currentUser]);

  useEffect(() => {
    function handlePopState() {
      const pathname = window.location.pathname;
      if ((pathname === "/cart" || pathname === "/orders" || pathname === "/owner") && !token) {
        window.history.replaceState({}, "", "/login");
        setCurrentView("account");
        setShowRegisterFields(false);
        setNotice("Inicia sesión con una cuenta verificada para continuar.");
        return;
      }
      if (pathname === "/owner" && currentUser && !currentUser.can_manage_store) {
        window.history.replaceState({}, "", "/home");
        setCurrentView("shop");
        setError("Tu cuenta no tiene permisos para gestionar el negocio.");
        return;
      }
      setCurrentView(viewForPath(pathname));
      setSelectedProductId(productIdForPath(pathname));
      setSelectedImageIndex(0);
      setShowRegisterFields(pathname === "/register");
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [token]);

  useEffect(() => {
    if ((view === "cart" || view === "orders") && !token) {
      window.history.replaceState({}, "", "/login");
      setCurrentView("account");
      setShowRegisterFields(false);
      setNotice("Inicia sesión con una cuenta verificada para continuar.");
    }
  }, [token, view]);

  useEffect(() => {
    if (!zelleAvailable && selectedPayment === "zelle") {
      setSelectedPayment("cash");
    }
  }, [zelleAvailable, selectedPayment]);

  useEffect(() => {
    if (token) loadOrders(token).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!token) {
      setCurrentUser(null);
      return;
    }
    api("/auth/me/", { token })
      .then(setCurrentUser)
      .catch((e) => {
        setCurrentUser(null);
        setError(e.message);
      });
  }, [token]);

  useEffect(() => {
    if (view !== "owner") return;
    if (!token) {
      setView("login");
      setNotice("Inicia sesión como dueño para acceder al panel del negocio.");
    } else if (currentUser && !currentUser.can_manage_store) {
      setView("shop");
      setError("Tu cuenta no tiene permisos para gestionar el negocio.");
    }
  }, [view, token, currentUser]);

  useEffect(() => {
    const verificationToken = new URLSearchParams(window.location.search).get(
      "verify",
    );
    if (!verificationToken) return;
    api("/auth/verify-email/", {
      method: "POST",
      body: { token: verificationToken },
    })
      .then((result) => {
        setNotice(result.detail);
        window.history.replaceState({}, "", window.location.pathname);
      })
      .catch((e) => setError(e.message));
  }, []);

  function addToCart(product) {
    if (!token) {
      setView("account");
      setNotice("Inicia sesión o crea una cuenta verificada para agregar artículos al carrito.");
      setError("");
      return;
    }
    const quantity = cart[product.id] || 0;
    if (quantity >= product.available_stock) {
      setError("No hay más unidades disponibles para agregar.");
      return;
    }
    setCart((current) => {
      return { ...current, [product.id]: quantity + 1 };
    });
    setError("");
    setRecentlyAddedId(product.id);
    setNotice(`${product.name} se agregó al carrito.`);
  }

  function openProduct(productId) {
    setView("product", productId);
  }

  function openCart() {
    if (!token) {
      setView("account");
      setNotice("Inicia sesión o crea una cuenta verificada para comprar.");
      setError("");
      return;
    }
    setView("cart");
  }

  function changeQuantity(product, quantity) {
    setCart((current) => {
      if (quantity <= 0) {
        const next = { ...current };
        delete next[product.id];
        return next;
      }
      if (quantity > product.available_stock) {
        setError("La cantidad supera el inventario disponible.");
        return current;
      }
      return { ...current, [product.id]: quantity };
    });
  }

  async function submitAuth(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const isRegister = form.get("mode") === "register";
    const body = isRegister
      ? {
          email: form.get("email"),
          password: form.get("password"),
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          phone: form.get("phone"),
        }
      : { email: form.get("email"), password: form.get("password") };
    try {
      const result = await api(
        isRegister ? "/auth/register/" : "/auth/login/",
        { method: "POST", body },
      );
      if (isRegister) {
        setNotice(result.detail);
      } else {
        sessionStorage.setItem("store-token", result.access);
        sessionStorage.setItem("store-refresh", result.refresh);
        setToken(result.access);
        const user = await api("/auth/me/", { token: result.access });
        setCurrentUser(user);
        setNotice("Sesión iniciada.");
        setView(user.can_manage_store ? "owner" : "shop");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function resendVerification() {
    const email = emailInput.current?.value.trim();
    if (!email) {
      setError("Escribe el correo de la cuenta que quieres verificar.");
      return;
    }
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const result = await api("/auth/resend-verification/", {
        method: "POST",
        body: { email },
      });
      setNotice(result.detail);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function checkout(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!token) {
      setView("account");
      setNotice("Inicia sesión o crea una cuenta verificada para realizar un pedido.");
      return;
    }
    const form = new FormData(event.currentTarget);
    const paymentMethod = form.get("payment_method");
    const proof = form.get("proof");
    if (paymentMethod !== "cash" && !proof?.size) {
      setError("Debes adjuntar la captura de la transferencia para crear el pedido.");
      return;
    }
    const confirmed = await confirmation.confirm({
      title: "Confirmar pedido",
      message: paymentMethod === "cash"
        ? "¿Confirmas que deseas crear este pedido en efectivo?"
        : "¿Confirmas que deseas crear este pedido y enviar la captura de la transferencia?",
      confirmLabel: "Crear pedido",
    });
    if (!confirmed) return;
    setBusy(true);
    try {
      const orderBody = new FormData();
      orderBody.append("items", JSON.stringify(cartProducts.map((item) => ({
        product_id: item.id,
        quantity: item.quantity,
      }))));
      orderBody.append("payment_method", paymentMethod);
      const transactionNumber = form.get("transaction_number");
      if (transactionNumber) orderBody.append("transaction_number", transactionNumber);
      orderBody.append("customer_note", form.get("customer_note") || "");
      if (paymentMethod !== "cash") orderBody.append("proof", proof);
      const order = await api("/orders/", {
        method: "POST",
        token,
        body: orderBody,
      });
      setCart(emptyCart);
      setProofPreview("");
      if (proofInput.current) proofInput.current.value = "";
      await loadOrders();
      setNotice(
        paymentMethod === "cash"
          ? `Pedido #${order.id} creado. El dueño coordinará contigo por WhatsApp; la reserva dura 24 horas.`
          : `Pedido #${order.id} creado con comprobante. Quedó pendiente de revisión manual.`,
      );
      setView("orders");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadProof(orderId) {
    const file = proofFiles[orderId];
    if (!file) {
      setError("Selecciona primero la captura del pago.");
      return;
    }
    const confirmed = await confirmation.confirm({
      title: "Enviar comprobante",
      message: `¿Enviar esta captura de pago para el pedido #${orderId}?`,
      confirmLabel: "Enviar captura",
    });
    if (!confirmed) return;
    const formElement = document.querySelector(`#proof-form-${orderId}`);
    const form = new FormData(formElement);
    form.set("image", file);
    setError("");
    setBusy(true);
    try {
      await api(`/orders/${orderId}/proof/`, {
        method: "POST",
        token,
        body: form,
      });
      await loadOrders();
      setNotice("Comprobante enviado para revisión.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelOrder(orderId) {
    const confirmed = await confirmation.confirm({
      title: "Cancelar pedido",
      message: `¿Seguro que deseas cancelar el pedido #${orderId}? Se liberará el inventario reservado.`,
      confirmLabel: "Cancelar pedido",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await api(`/orders/${orderId}/cancel/`, { method: "POST", token });
      await loadOrders();
      setNotice("Pedido cancelado y reserva liberada.");
    } catch (e) {
      setError(e.message);
    }
  }

  async function openProof(url) {
    const proofWindow = window.open("about:blank", "_blank");
    try {
      const blob = await api(url, { token, responseType: "blob" });
      const objectUrl = URL.createObjectURL(blob);
      if (proofWindow) proofWindow.location = objectUrl;
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (e) {
      proofWindow?.close();
      setError(e.message);
    }
  }

  function signOut() {
    confirmation.confirm({
      title: "Cerrar sesión",
      message: "¿Quieres cerrar tu sesión? El carrito de esta sesión se vaciará.",
      confirmLabel: "Cerrar sesión",
      danger: true,
    }).then((confirmed) => {
      if (!confirmed) return;
      sessionStorage.removeItem("store-token");
      sessionStorage.removeItem("store-refresh");
      setToken(null);
      setCurrentUser(null);
      setCart(emptyCart);
      setOrders([]);
      setView("shop");
    });
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/home" onClick={(event) => { event.preventDefault(); setView("shop"); }}>
          <span className="brand-mark">G</span>
          <span>{settings?.store_name || "Tienda Gamer Cuba"}</span>
        </a>
        <nav>
          <button className={view === "shop" ? "nav-active" : ""} onClick={() => setView("shop")}>
            Tienda
          </button>
          <button
            className={`nav-cart-button${view === "cart" ? " nav-active" : ""}`}
            onClick={openCart}
            aria-label={`Carrito, ${cartCount} artículos`}
            title="Carrito"
          >
            <img
              className="cart-icon"
              src="/shopping-cart-01-svgrepo-com.svg"
              alt=""
              aria-hidden="true"
            />
            <span className="count">{cartCount}</span>
          </button>
          {token && (
            <button className={view === "orders" ? "nav-active" : ""} onClick={() => setView("orders")}>
              Mis pedidos
            </button>
          )}
          {currentUser?.can_manage_store && (
            <button className={view === "owner" ? "nav-active" : ""} onClick={() => setView("owner")}>
              Panel del negocio
            </button>
          )}
          {token ? (
            <button className="account-button" onClick={signOut}>Salir</button>
          ) : (
            <button className="account-button" onClick={() => setView("login")}>Entrar</button>
          )}
        </nav>
      </header>

      {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice("")}>×</button></div>}
      {error && <div className="error" role="alert">{error}<button onClick={() => setError("")}>×</button></div>}
      <ConfirmationDialog
        dialog={confirmation.dialog}
        onResolve={confirmation.resolveDialog}
      />

      {view === "shop" && (
        <main>
          <section className="hero">
            <div className="hero-copy">
              <p className="eyebrow">GAMING · ACCESORIOS · VIDEOJUEGOS</p>
              <h1>Tu próximo nivel<br /><span>empieza aquí.</span></h1>
              <p>Encuentra consolas, juegos y accesorios. Compra online y coordina tu recogida por WhatsApp.</p>
              <button className="primary-button" onClick={() => document.getElementById("catalogo").scrollIntoView({ behavior: "smooth" })}>
                Explorar catálogo <span>↓</span>
              </button>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="hero-orbit orbit-one" />
              <div className="hero-orbit orbit-two" />
              <div className="controller">⌕</div>
              <div className="hero-chip">PLAY<br />MORE</div>
            </div>
            <div className="hero-bottom"><span>01 / EXPERIENCIA GAMER</span><span>COMPRA SEGURA · REVISIÓN MANUAL</span></div>
          </section>

          <section className="catalog section-wrap" id="catalogo">
            <div className="section-heading">
              <div><p className="eyebrow">SELECCIÓN DE LA TIENDA</p><h2>Encuentra tu equipo</h2></div>
              <span className="product-count">{visibleProducts.length} artículos</span>
            </div>
            <div className="category-list">
              {categories.map((item) => (
                <button key={item} className={category === item ? "category active" : "category"} onClick={() => setCategory(item)}>{item}</button>
              ))}
            </div>
            {visibleProducts.length ? (
              <div className="product-grid">
                {visibleProducts.map((product) => (
                  <article className="product-card" key={product.id}>
                    <div className="product-photo">
                      <a
                        className="product-detail-link"
                        href={`/product/${product.id}`}
                        aria-label={`Ver detalles de ${product.name}`}
                        onClick={(event) => {
                          event.preventDefault();
                          openProduct(product.id);
                        }}
                      >
                        {product.images[0] ? (
                          <img src={product.images[0].image_url} alt={product.images[0].alt_text || product.name} />
                        ) : <div className="photo-placeholder"><span>✳</span><small>{product.category}</small></div>}
                      </a>
                      {product.zelle_eligible && <span className="product-tag">ZELLE DISPONIBLE</span>}
                    </div>
                    <div className="product-info">
                      <p className="product-category">{product.category}</p>
                      <h3><a href={`/product/${product.id}`} onClick={(event) => { event.preventDefault(); openProduct(product.id); }}>{product.name}</a></h3>
                      <p className="product-description">{product.description || "Artículo gamer disponible en la tienda."}</p>
                      <div className="product-bottom">
                        <div><strong>{money(product.price_cup)}</strong><small>{product.available_stock} disponibles</small></div>
                        <button className={`add-button${recentlyAddedId === product.id ? " added" : ""}`} aria-label={token ? `Agregar ${product.name}` : `Inicia sesión para agregar ${product.name}`} title={token ? "Agregar al carrito" : "Inicia sesión para comprar"} disabled={!product.available_stock} onClick={() => addToCart(product)}>{recentlyAddedId === product.id ? "✓" : "+"}</button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : <div className="empty-state"><span>◌</span><h3>Próximamente</h3><p>El catálogo se está preparando. Vuelve pronto.</p></div>}
          </section>

          <section className="how-it-works">
            <div><p className="eyebrow">SENCILLO Y TRANSPARENTE</p><h2>Así funciona tu compra</h2></div>
            <div className="steps">
              <div><span>01</span><h3>Arma tu carrito</h3><p>Elige lo que necesitas y revisa el precio en CUP.</p></div>
              <div><span>02</span><h3>Envía tu pedido</h3><p>Selecciona pago y adjunta el comprobante si corresponde.</p></div>
              <div><span>03</span><h3>Coordina la recogida</h3><p>El dueño revisa el pago y coordina contigo por WhatsApp.</p></div>
            </div>
          </section>
        </main>
      )}

      {view === "product" && (
        <main className="section-wrap page-section product-detail-page">
          {selectedProduct ? (
            <>
              <button className="back-link" onClick={() => setView("shop")}>← Volver al catálogo</button>
              <div className="product-detail-layout">
                <div className="product-gallery">
                  <div className="product-main-image">
                    {selectedProduct.images[selectedImageIndex] ? (
                      <img
                        src={selectedProduct.images[selectedImageIndex].image_url}
                        alt={selectedProduct.images[selectedImageIndex].alt_text || selectedProduct.name}
                      />
                    ) : (
                      <div className="photo-placeholder"><span>✳</span><small>{selectedProduct.category}</small></div>
                    )}
                    {selectedProduct.zelle_eligible && <span className="product-tag">ZELLE DISPONIBLE</span>}
                  </div>
                  {selectedProduct.images.length > 1 && (
                    <div className="product-thumbnails">
                      {selectedProduct.images.map((image, index) => (
                        <button
                          className={index === selectedImageIndex ? "thumbnail active" : "thumbnail"}
                          key={image.id}
                          aria-label={`Ver foto ${index + 1}`}
                          onClick={() => setSelectedImageIndex(index)}
                        >
                          <img src={image.image_url} alt={image.alt_text || `${selectedProduct.name}, foto ${index + 1}`} />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div className="product-detail-info">
                  <p className="product-category">{selectedProduct.category}</p>
                  <h1>{selectedProduct.name}</h1>
                  <strong className="product-detail-price">{money(selectedProduct.price_cup)}</strong>
                  <p className="product-detail-stock">{selectedProduct.available_stock > 0 ? `${selectedProduct.available_stock} disponibles` : "Agotado"}</p>
                  <div className="product-detail-description">
                    <h2>Descripción</h2>
                    <p>{selectedProduct.description || "Artículo gamer disponible en la tienda."}</p>
                  </div>
                  <button
                    className="primary-button product-detail-add"
                    disabled={!selectedProduct.available_stock}
                    onClick={() => addToCart(selectedProduct)}
                  >
                    {recentlyAddedId === selectedProduct.id ? "Agregado ✓" : "Agregar al carrito"}
                  </button>
                  {!token && <p className="small-note">Inicia sesión con una cuenta verificada para comprar.</p>}
                  {selectedProduct.zelle_eligible && <p className="small-note">Zelle disponible para este producto; importe a coordinar por WhatsApp.</p>}
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state"><h3>No encontramos este producto</h3><button className="primary-button" onClick={() => setView("shop")}>Volver a la tienda</button></div>
          )}
        </main>
      )}

      {view === "cart" && (
        <main className="section-wrap page-section">
          <div className="section-heading"><div><p className="eyebrow">TU SELECCIÓN</p><h2>Carrito</h2></div></div>
          {!cartProducts.length ? <div className="empty-state"><span>◌</span><h3>Tu carrito está vacío</h3><p>Explora la tienda y agrega tus artículos favoritos.</p><button className="primary-button" onClick={() => setView("shop")}>Ir a la tienda</button></div> : (
            <div className="checkout-layout">
              <div className="cart-list">
                {cartProducts.map((item) => (
                  <div className="cart-row" key={item.id}>
                    <div className="cart-thumb">{item.images[0] ? <img src={item.images[0].image_url} alt="" /> : "✳"}</div>
                    <div className="cart-product"><p>{item.category}</p><h3>{item.name}</h3><strong>{money(item.price_cup)}</strong></div>
                    <div className="quantity">
                      <button onClick={() => changeQuantity(item, item.quantity - 1)}>−</button><span>{item.quantity}</span><button onClick={() => changeQuantity(item, item.quantity + 1)}>+</button>
                    </div>
                    <strong className="line-total">{money(item.price_cup * item.quantity)}</strong>
                  </div>
                ))}
              </div>
              <form className="checkout-card" onSubmit={checkout}>
                <p className="eyebrow">RESUMEN DEL PEDIDO</p>
                <div className="summary-line"><span>Artículos ({cartCount})</span><span>{money(cartTotal)}</span></div>
                <div className="summary-total"><span>Total</span><strong>{money(cartTotal)}</strong></div>
                <p className="small-note">{settings?.pickup_instructions || "La recogida se coordina individualmente por WhatsApp."} Los artículos se reservan por 24 horas.</p>
                <label className="field-label">Método de pago</label>
                <select name="payment_method" value={selectedPayment} onChange={(event) => setSelectedPayment(event.target.value)} required>
                  <option value="cash">Efectivo CUP</option>
                  <option value="bpa">Transferencia a tarjeta BPA</option>
                  <option value="mobile">Transferencia de saldo móvil</option>
                  {zelleAvailable && <option value="zelle">Zelle (importe a coordinar por WhatsApp)</option>}
                </select>
                <div className="payment-instructions">
                  {selectedPayment === "cash" ? (
                    <p>Contacta al dueño por WhatsApp ({settings?.whatsapp_number || "5350000000"}) para coordinar pago y recogida.</p>
                  ) : selectedPayment === "bpa" ? (
                    <>
                      <p>Realiza la transferencia a esta tarjeta BPA:</p>
                      <strong>{settings?.bpa_card_number || "0000-0000-0000-0000"}</strong>
                      {paymentInstructions && <p>{paymentInstructions}</p>}
                    </>
                  ) : selectedPayment === "zelle" ? (
                    <>
                      <p>Envía el pago a esta cuenta Zelle (importe a coordinar por WhatsApp):</p>
                      <strong>{settings?.zelle_account || "zelle@example.com"}</strong>
                      {paymentInstructions && <p>{paymentInstructions}</p>}
                    </>
                  ) : (
                    <>
                      <p>Realiza la transferencia de saldo móvil al WhatsApp del dueño: <a href={`https://wa.me/${(settings?.whatsapp_number || "5350000000").replace(/\D/g, "")}`} target="_blank" rel="noreferrer"><strong>{settings?.whatsapp_number || "5350000000"}</strong></a>.</p>
                      {paymentInstructions && <p>{paymentInstructions}</p>}
                    </>
                  )}
                </div>
                {["bpa", "zelle"].includes(selectedPayment) && <>
                  <label className="field-label">Número de transacción <span>(obligatorio)</span></label>
                  <input name="transaction_number" maxLength="100" required placeholder="Escribe el número de transacción" />
                </>}
                <label className="field-label">Nota para el dueño <span>(opcional)</span></label>
                <textarea name="customer_note" rows="2" placeholder="Detalles para coordinar la recogida" />
                <label className="field-label">{selectedPayment === "cash" ? "Captura del pago" : "Captura de la transferencia (obligatoria)"} <span>(JPG, PNG o WEBP; hasta 5 MB)</span></label>
                <input
                  ref={proofInput}
                  name="proof"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  required={selectedPayment !== "cash"}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    setProofPreview(file ? URL.createObjectURL(file) : "");
                  }}
                />
                {proofPreview && (
                  <div className="proof-preview">
                    <img src={proofPreview} alt="Vista previa del comprobante seleccionado" />
                    <div className="proof-preview-details">
                      <span>{proofInput.current?.files?.[0]?.name}</span>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => {
                          if (proofInput.current) proofInput.current.value = "";
                          setProofPreview("");
                        }}
                      >
                        Quitar imagen
                      </button>
                    </div>
                  </div>
                )}
                <button className="primary-button full-width" disabled={busy}>{busy ? "Procesando..." : token ? "Realizar pedido" : "Entrar para continuar"}</button>
                {!token && <p className="small-note">Necesitas una cuenta verificada para realizar el pedido.</p>}
              </form>
            </div>
          )}
        </main>
      )}

      {view === "account" && (
        <main className="section-wrap page-section">
          <div className="section-heading"><div><p className="eyebrow">TU CUENTA</p><h2>Bienvenido</h2></div></div>
          <div className="account-layout">
            <div className="account-intro"><span className="account-symbol">◎</span><h3>Compra con tranquilidad</h3><p>Regístrate para hacer pedidos, enviar comprobantes y consultar el estado de tus compras.</p></div>
            <form className="account-form" onSubmit={submitAuth}>
              <div className="auth-toggle"><label><input type="radio" name="mode" value="login" checked={!showRegisterFields} onChange={() => setView("login")} /> Iniciar sesión</label><label><input type="radio" name="mode" value="register" checked={showRegisterFields} onChange={() => setView("register")} /> Crear cuenta</label></div>
              <div className="register-fields" hidden={!showRegisterFields}>
              <div className="form-row"><label><span>Nombre</span><input name="first_name" required={showRegisterFields} /></label><label><span>Apellidos</span><input name="last_name" required={showRegisterFields} /></label></div>
              <label><span>Celular</span><input name="phone" type="tel" required={showRegisterFields} placeholder="+53..." /></label>
              </div>
              <label><span>Correo electrónico</span><input ref={emailInput} name="email" type="email" autoComplete="email" required /></label>
              <label><span>Contraseña</span><input name="password" type="password" autoComplete={showRegisterFields ? "new-password" : "current-password"} required minLength={showRegisterFields ? 8 : undefined} /></label>
              <button className="primary-button full-width" disabled={busy}>{busy ? "Un momento..." : showRegisterFields ? "Crear cuenta" : "Iniciar sesión"}</button>
              {showRegisterFields && <>
                <p className="small-note">Verifica tu correo desde el enlace enviado para poder iniciar sesión. Si no te llegó, puedes solicitar otro.</p>
                <button className="text-button" type="button" disabled={busy} onClick={resendVerification}>Reenviar enlace de verificación</button>
              </>}
              {!showRegisterFields && <p className="small-note">Para iniciar sesión, tu correo debe estar verificado.</p>}
            </form>
          </div>
        </main>
      )}

      {view === "orders" && (
        <main className="section-wrap page-section">
          <div className="section-heading"><div><p className="eyebrow">HISTORIAL</p><h2>Mis pedidos</h2></div></div>
          {!orders.length ? <div className="empty-state"><h3>Aún no tienes pedidos</h3><button className="primary-button" onClick={() => setView("shop")}>Explorar tienda</button></div> : (
            <div className="orders-list">
              {orders.map((order) => (
                <article className="order-card" key={order.id}>
                  <div className="order-header"><div><p className="eyebrow">PEDIDO #{order.id}</p><span>{new Date(order.created_at).toLocaleString("es-CU")}</span></div><span className={`status status-${order.status}`}>{order.status_label}</span></div>
                  <div className="order-items">{order.items.map((item, index) => <div key={index}><span>{item.quantity} × {item.product_name}</span><span>{money(item.line_total_cup)}</span></div>)}</div>
                  <div className="order-footer"><span>{order.payment_method_label}</span><strong>{money(order.total_cup)}</strong></div>
                  {order.payment_rejection_reason && <p className="rejection-reason"><strong>Motivo:</strong> {order.payment_rejection_reason}</p>}
                  {order.proofs?.length > 0 && <div className="proof-list">{order.proofs.map((proof) => <button className="proof-link" key={proof.id} type="button" onClick={() => openProof(proof.proof_url)}>Ver comprobante · {new Date(proof.submitted_at).toLocaleDateString("es-CU")}</button>)}</div>}
                  {order.payment_method !== "cash" && ["pending", "payment_rejected", "proof_submitted"].includes(order.status) && (
                    <form id={`proof-form-${order.id}`} className="proof-upload" onSubmit={(e) => { e.preventDefault(); uploadProof(order.id); }}>
                      <p>{order.status === "payment_rejected" ? "Envía una nueva captura para corregir el comprobante." : order.status === "proof_submitted" ? "Si necesitas corregirlo, puedes enviar otra captura." : "Adjunta una captura de tu transferencia para que el dueño la revise."}</p>
                      <div className="proof-actions"><input type="file" accept="image/jpeg,image/png,image/webp" required onChange={(e) => setProofFiles({ ...proofFiles, [order.id]: e.target.files[0] })} />{["bpa", "zelle"].includes(order.payment_method) && <input name="transaction_number" placeholder="N.º de transacción (obligatorio)" defaultValue={order.transaction_number} required />}<button className="secondary-button" disabled={busy}>Enviar captura</button></div>
                    </form>
                  )}
                  {["pending", "proof_submitted", "payment_rejected"].includes(order.status) && <div className="order-actions"><p>Reserva hasta {new Date(order.reservation_expires_at).toLocaleString("es-CU")}. Coordina recogida por WhatsApp.</p><button className="text-button" onClick={() => cancelOrder(order.id)}>Cancelar pedido</button></div>}
                </article>
              ))}
            </div>
          )}
        </main>
      )}

      {view === "owner" && currentUser?.can_manage_store && (
        <OwnerDashboard token={token} openProof={openProof} money={money} />
      )}

      <footer className="footer">
        <div><a className="brand" href="/home" onClick={(event) => { event.preventDefault(); setView("shop"); }}><span className="brand-mark">G</span><span>{settings?.store_name || "Tienda Gamer Cuba"}</span></a><p>Gaming y tecnología, más cerca de ti.</p></div>
        <div className="footer-contact"><strong>¿Necesitas ayuda?</strong><p>La recogida y los pagos en efectivo se coordinan con el dueño.</p><p>Cambios y devoluciones: {settings?.returns_policy || "No se aceptan cambios ni devoluciones."}</p>{settings?.whatsapp_number && <a href={`https://wa.me/${settings.whatsapp_number.replace(/\D/g, "")}`} target="_blank" rel="noreferrer">Escribir por WhatsApp ↗</a>}</div>
        <span className="copyright">© {new Date().getFullYear()} · Precios expresados en CUP</span>
      </footer>
    </div>
  );
}

export default App;
