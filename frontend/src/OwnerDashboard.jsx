import { useEffect, useState } from "react";
import { api } from "./api.js";
import ConfirmationDialog, { useConfirmationDialog } from "./ConfirmationDialog.jsx";

const emptyProduct = {
  name: "",
  description: "",
  category: "",
  price_cup: "",
  stock: "",
  is_active: true,
  image_urls: "",
};

const emptySettings = {
  store_name: "",
  whatsapp_number: "",
  bpa_card_number: "",
  zelle_account: "",
  bpa_instructions: "",
  mobile_balance_instructions: "",
  zelle_instructions: "",
  pickup_instructions: "",
  returns_policy: "",
};

function OwnerDashboard({ token, openProof, money }) {
  const confirmation = useConfirmationDialog();
  const [tab, setTab] = useState("orders");
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [orders, setOrders] = useState([]);
  const [settings, setSettings] = useState(emptySettings);
  const [productForm, setProductForm] = useState(emptyProduct);
  const [editingId, setEditingId] = useState(null);
  const [categoryName, setCategoryName] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [rejectionReasons, setRejectionReasons] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadPanel() {
    setLoading(true);
    setError("");
    try {
      const [productData, categoryData, orderData, storeSettings] =
        await Promise.all([
          api("/owner/products/", { token }),
          api("/owner/categories/", { token }),
          api("/owner/orders/", { token }),
          api("/owner/settings/", { token }),
        ]);
      setProducts(productData);
      setCategories(categoryData);
      setOrders(orderData);
      setSettings(storeSettings);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPanel();
  }, [token]);

  useEffect(() => {
    if (!notice) return undefined;
    const timeout = window.setTimeout(() => setNotice(""), 4500);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  const pendingCount = orders.filter((order) =>
    ["pending", "proof_submitted", "payment_rejected"].includes(order.status),
  ).length;
  const shownOrders = statusFilter
    ? orders.filter((order) => order.status === statusFilter)
    : orders;

  function beginEdit(product) {
    setEditingId(product.id);
    setProductForm({
      name: product.name,
      description: product.description || "",
      category: product.category ? String(product.category) : "",
      price_cup: String(product.price_cup),
      stock: String(product.stock),
      is_active: product.is_active,
      image_urls: (product.images || [])
        .map((image) => image.image_url)
        .filter(Boolean)
        .join("\n"),
    });
    setTab("products");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function resetProductForm() {
    setEditingId(null);
    setProductForm({
      ...emptyProduct,
      category: categories[0] ? String(categories[0].id) : "",
    });
  }

  async function saveProduct(event) {
    event.preventDefault();
    const confirmed = await confirmation.confirm({
      title: editingId ? "Guardar producto" : "Agregar producto",
      message: editingId ? "¿Confirmas guardar los cambios de este producto?" : "¿Confirmas agregar este producto al inventario?",
      confirmLabel: editingId ? "Guardar cambios" : "Agregar",
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    const images = productForm.image_urls
      .split(/\r?\n/)
      .map((url) => url.trim())
      .filter(Boolean)
      .map((image_url, sort_order) => ({
        image_url,
        sort_order,
        alt_text: productForm.name,
      }));
    const payload = {
      name: productForm.name.trim(),
      description: productForm.description,
      category: Number(productForm.category),
      price_cup: Number(productForm.price_cup),
      stock: Number(productForm.stock),
      is_active: productForm.is_active,
      images,
    };
    try {
      await api(
        editingId ? `/owner/products/${editingId}/` : "/owner/products/",
        {
          token,
          method: editingId ? "PATCH" : "POST",
          body: payload,
        },
      );
      await loadPanel();
      setNotice(editingId ? "Producto actualizado." : "Producto agregado al inventario.");
      resetProductForm();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function addCategory(event) {
    event.preventDefault();
    const confirmed = await confirmation.confirm({
      title: "Crear categoría",
      message: `¿Crear la categoría «${categoryName.trim()}»?`,
      confirmLabel: "Crear categoría",
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api("/owner/categories/", {
        token,
        method: "POST",
        body: { name: categoryName.trim(), is_active: true },
      });
      setCategoryName("");
      await loadPanel();
      setNotice("Categoría creada.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function editCategory(category) {
    const name = await confirmation.confirm({
      title: "Editar categoría",
      message: `Escribe el nuevo nombre para «${category.name}».`,
      inputLabel: "Nombre de la categoría",
      inputValue: category.name,
      confirmLabel: "Continuar",
      maxLength: 80,
    });
    if (!name || name === category.name) return;
    const confirmed = await confirmation.confirm({
      title: "Confirmar cambio",
      message: `¿Cambiar el nombre de «${category.name}» a «${name}»?`,
      confirmLabel: "Guardar nombre",
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api(`/owner/categories/${category.id}/`, {
        token,
        method: "PATCH",
        body: { name: name.trim() },
      });
      await loadPanel();
      setNotice("Categoría actualizada.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteCategory(category) {
    const affectedProducts = products.filter((product) => product.category === category.id).length;
    const detail = affectedProducts
      ? ` ${affectedProducts} producto(s) quedarán sin categoría y tendrás que asignarles otra antes de editarlos.`
      : "";
    const confirmed = await confirmation.confirm({
      title: "Eliminar categoría",
      message: `¿Eliminar la categoría «${category.name}»?${detail} Esta acción no se puede deshacer.`,
      confirmLabel: "Eliminar categoría",
      danger: true,
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api(`/owner/categories/${category.id}/`, {
        token,
        method: "DELETE",
      });
      if (editingId && products.some((product) => product.id === editingId && product.category === category.id)) {
        resetProductForm();
      }
      await loadPanel();
      setNotice(`Categoría eliminada.${affectedProducts ? ` ${affectedProducts} producto(s) quedaron sin categoría.` : ""}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleProduct(product) {
    const confirmed = await confirmation.confirm({
      title: product.is_active ? "Ocultar producto" : "Publicar producto",
      message: product.is_active ? `¿Ocultar «${product.name}» de la tienda?` : `¿Publicar «${product.name}» en la tienda?`,
      confirmLabel: product.is_active ? "Ocultar" : "Publicar",
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      await api(`/owner/products/${product.id}/`, {
        token,
        method: "PATCH",
        body: { is_active: !product.is_active },
      });
      await loadPanel();
      setNotice(product.is_active ? "Producto ocultado de la tienda." : "Producto publicado.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function orderAction(order, action, body = {}) {
    const confirmationMessage = {
      approve: `¿Confirmas que recibiste el pago del pedido #${order.id}?`,
      reject: `¿Rechazar el comprobante del pedido #${order.id}?`,
      preparing: `¿Empezar a preparar el pedido #${order.id}?`,
      ready: `¿Marcar el pedido #${order.id} como listo para recoger?`,
      complete: `¿Marcar el pedido #${order.id} como completado?`,
    }[action];
    if (confirmationMessage) {
      const confirmed = await confirmation.confirm({
        title: action === "approve" ? "Aprobar pedido" : action === "reject" ? "Rechazar comprobante" : "Actualizar pedido",
        message: confirmationMessage,
        confirmLabel: action === "approve" ? "Aprobar pedido" : action === "reject" ? "Rechazar" : "Confirmar",
        danger: action === "reject",
      });
      if (!confirmed) return;
    }
    setBusy(true);
    setError("");
    try {
      await api(`/owner/orders/${order.id}/${action}/`, {
        token,
        method: "POST",
        body,
      });
      await loadPanel();
      setNotice(
        action === "approve"
          ? `Pedido #${order.id} aprobado; se descontó el inventario.`
          : action === "reject"
            ? `Comprobante del pedido #${order.id} rechazado.`
            : `Estado del pedido #${order.id} actualizado.`,
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    const confirmed = await confirmation.confirm({
      title: "Guardar datos del negocio",
      message: "¿Guardar los cambios de contacto y pago del negocio?",
      confirmLabel: "Guardar cambios",
    });
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api("/owner/settings/", {
        token,
        method: "PATCH",
        body: settings,
      });
      setSettings(updated);
      setNotice("Datos de la tienda guardados.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="owner-page">
      <ConfirmationDialog
        dialog={confirmation.dialog}
        onResolve={confirmation.resolveDialog}
      />
      <section className="owner-heading">
        <div>
          <p className="eyebrow">GESTIÓN PRIVADA</p>
          <h1>Panel del negocio</h1>
          <p>Inventario, pedidos y pagos en un solo lugar.</p>
        </div>
        <div className="owner-stat">
          <strong>{pendingCount}</strong>
          <span>pedidos por revisar</span>
        </div>
      </section>

      {notice && <div className="owner-notice" role="status">{notice}</div>}
      {error && <div className="owner-error" role="alert">{error}</div>}

      <nav className="owner-tabs" aria-label="Secciones del panel">
        <button className={tab === "orders" ? "active" : ""} onClick={() => setTab("orders")}>Pedidos {pendingCount > 0 && <span>{pendingCount}</span>}</button>
        <button className={tab === "products" ? "active" : ""} onClick={() => setTab("products")}>Inventario</button>
        <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>Datos y pagos</button>
      </nav>

      {loading ? <div className="owner-loading">Cargando datos del negocio…</div> : <>
        {tab === "orders" && (
          <section className="owner-section">
            <div className="owner-section-heading">
              <div><p className="eyebrow">VENTAS</p><h2>Pedidos</h2></div>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filtrar pedidos por estado">
                <option value="">Todos los estados</option>
                <option value="pending">Pendiente</option>
                <option value="proof_submitted">Comprobante recibido</option>
                <option value="payment_rejected">Comprobante rechazado</option>
                <option value="confirmed">Confirmado</option>
                <option value="preparing">Preparando</option>
                <option value="ready">Listo para recoger</option>
                <option value="completed">Completado</option>
                <option value="cancelled">Cancelado</option>
                <option value="expired">Reserva vencida</option>
              </select>
            </div>
            {shownOrders.length === 0 ? <div className="owner-empty">No hay pedidos en esta lista.</div> : (
              <div className="owner-orders">
                {shownOrders.map((order) => (
                  <article className="owner-order" key={order.id}>
                    <header className="owner-order-header">
                      <div><p className="eyebrow">PEDIDO #{order.id}</p><span>{new Date(order.created_at).toLocaleString("es-CU")}</span></div>
                      <span className={`status status-${order.status}`}>{order.status_label}</span>
                    </header>
                    <div className="owner-customer">
                      <h3>Datos del cliente</h3>
                      <p><strong>{order.customer_name || "Sin nombre"}</strong></p>
                      <p><a href={`mailto:${order.customer_email}`}>{order.customer_email}</a> · <a href={`tel:${order.customer_phone}`}>{order.customer_phone}</a></p>
                    </div>
                    <div className="owner-order-items">
                      <h3>Artículos</h3>
                      {order.items.map((item, index) => (
                        <div className="owner-order-item" key={index}>
                          {item.product_image_url ? (
                            <img className="owner-order-item-image" src={item.product_image_url} alt={item.product_name} />
                          ) : (
                            <span className="owner-order-item-image owner-order-item-placeholder" aria-label="Sin foto">✳</span>
                          )}
                          <span className="owner-order-item-info">
                            <strong>{item.product_name}</strong>
                            <small>{item.category_name || "Sin categoría"} · {money(item.unit_price_cup)} c/u</small>
                            <small>Cantidad: {item.quantity}</small>
                          </span>
                          <strong className="owner-order-item-total">{money(item.line_total_cup)}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="owner-order-summary">
                      <span>{order.payment_method_label}{order.transaction_number && ` · Transacción: ${order.transaction_number}`}</span>
                      <strong>{money(order.total_cup)}</strong>
                    </div>
                    {order.customer_note && <p className="owner-customer-note"><strong>Nota:</strong> {order.customer_note}</p>}
                    {order.payment_rejection_reason && <p className="rejection-reason"><strong>Motivo de rechazo:</strong> {order.payment_rejection_reason}</p>}
                    {order.proofs?.length > 0 && <div className="owner-proofs"><h3>Comprobantes de pago</h3>{order.proofs.map((proof) => <button type="button" key={proof.id} onClick={() => openProof(proof.proof_url)}>Abrir captura · {new Date(proof.submitted_at).toLocaleString("es-CU")}</button>)}</div>}
                    {order.payment_method !== "cash" && ["pending", "proof_submitted", "payment_rejected"].includes(order.status) && (
                      <div className="owner-order-actions">
                        <p>{order.proofs?.length ? "Confirma solo después de comprobar que el dinero fue recibido." : "Aún no se ha recibido una captura de pago."}</p>
                        {order.proofs?.length > 0 && <button className="primary-button" disabled={busy} onClick={() => orderAction(order, "approve")}>Pago recibido · Aprobar pedido</button>}
                        <div className="reject-form">
                          <input value={rejectionReasons[order.id] || ""} onChange={(event) => setRejectionReasons({ ...rejectionReasons, [order.id]: event.target.value })} placeholder="Motivo si el pago no coincide" />
                          <button className="secondary-button" disabled={busy || !rejectionReasons[order.id]?.trim()} onClick={() => orderAction(order, "reject", { reason: rejectionReasons[order.id] })}>Rechazar comprobante</button>
                        </div>
                      </div>
                    )}
                    {order.payment_method === "cash" && order.status === "pending" && (
                      <div className="owner-order-actions">
                        <p>Pedido en efectivo: coordina pago y recogida por WhatsApp antes de aprobar.</p>
                        <button className="primary-button" disabled={busy} onClick={() => orderAction(order, "approve")}>Confirmar pedido</button>
                      </div>
                    )}
                    {order.status === "confirmed" && <button className="secondary-button" disabled={busy} onClick={() => orderAction(order, "preparing")}>Empezar a preparar</button>}
                    {order.status === "preparing" && <button className="secondary-button" disabled={busy} onClick={() => orderAction(order, "ready")}>Marcar listo para recoger</button>}
                    {order.status === "ready" && <button className="secondary-button" disabled={busy} onClick={() => orderAction(order, "complete")}>Marcar como completado</button>}
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {tab === "products" && (
          <section className="owner-section">
            <div className="owner-section-heading"><div><p className="eyebrow">CATÁLOGO</p><h2>{editingId ? "Editar producto" : "Agregar producto"}</h2></div></div>
            <div className="owner-product-layout">
              <form className="owner-form" onSubmit={saveProduct}>
                <label>Nombre<input required maxLength="160" value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></label>
                <label>Categoría<select required value={productForm.category} onChange={(event) => setProductForm({ ...productForm, category: event.target.value })}><option value="">Selecciona categoría</option>{categories.filter((category) => category.is_active).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
                <div className="form-row">
                  <label>Precio CUP<input required type="number" min="1" step="1" value={productForm.price_cup} onChange={(event) => setProductForm({ ...productForm, price_cup: event.target.value })} /></label>
                  <label>Stock total<input required type="number" min="0" step="1" value={productForm.stock} onChange={(event) => setProductForm({ ...productForm, stock: event.target.value })} /></label>
                </div>
                <label>Descripción<textarea rows="4" value={productForm.description} onChange={(event) => setProductForm({ ...productForm, description: event.target.value })} /></label>
                <label>Enlaces de fotos <span>(uno por línea, HTTP/HTTPS)</span><textarea rows="3" placeholder="https://..." value={productForm.image_urls} onChange={(event) => setProductForm({ ...productForm, image_urls: event.target.value })} /></label>
                <label className="owner-checkbox"><input type="checkbox" checked={productForm.is_active} onChange={(event) => setProductForm({ ...productForm, is_active: event.target.checked })} /> Publicado en la tienda</label>
                <div className="owner-form-actions"><button className="primary-button" disabled={busy || categories.filter((category) => category.is_active).length === 0}>{busy ? "Guardando…" : editingId ? "Guardar cambios" : "Agregar producto"}</button>{editingId && <button className="secondary-button" type="button" onClick={resetProductForm}>Cancelar edición</button>}</div>
              </form>
              <div className="owner-category-box">
                <h3>Categorías</h3>
                <form onSubmit={addCategory}><input required maxLength="80" value={categoryName} onChange={(event) => setCategoryName(event.target.value)} placeholder="Nueva categoría" /><button className="secondary-button" disabled={busy}>Crear</button></form>
                <ul>{categories.map((category) => <li key={category.id}><span>{category.name}</span><small>{category.is_active ? "Activa" : "Inactiva"}</small><div><button type="button" disabled={busy} onClick={() => editCategory(category)}>Editar</button><button type="button" disabled={busy} onClick={() => deleteCategory(category)}>Eliminar</button></div></li>)}</ul>
                {categories.length === 0 && <p>Crea una categoría para agregar productos.</p>}
              </div>
            </div>
            <div className="owner-section-heading inventory-heading"><div><p className="eyebrow">EXISTENCIAS</p><h2>Inventario</h2></div><span>{products.length} productos</span></div>
            {products.length === 0 ? <div className="owner-empty">Aún no hay productos cargados.</div> : (
              <div className="inventory-table-wrap">
                <table className="inventory-table">
                  <thead><tr><th>Producto</th><th>Categoría</th><th>Precio</th><th>Stock</th><th>Reservado</th><th>Disponible</th><th>Estado</th><th /></tr></thead>
                  <tbody>{products.map((product) => <tr key={product.id}>
                    <td><strong>{product.name}</strong></td><td>{product.category_name}</td><td>{money(product.price_cup)}</td><td>{product.stock}</td><td>{product.reserved_stock}</td><td>{product.available_stock}</td><td>{product.is_active ? "Publicado" : "Oculto"}</td>
                    <td className="inventory-actions"><button onClick={() => beginEdit(product)}>Editar</button><button onClick={() => toggleProduct(product)} disabled={busy}>{product.is_active ? "Ocultar" : "Publicar"}</button></td>
                  </tr>)}</tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {tab === "settings" && (
          <section className="owner-section owner-settings">
            <div className="owner-section-heading"><div><p className="eyebrow">CONTACTO Y COBROS</p><h2>Datos del negocio</h2></div></div>
            <form className="owner-form settings-form" onSubmit={saveSettings}>
              <label>Nombre de la tienda<input value={settings.store_name} onChange={(event) => setSettings({ ...settings, store_name: event.target.value })} /></label>
              <label>WhatsApp para efectivo y saldo móvil<input value={settings.whatsapp_number} onChange={(event) => setSettings({ ...settings, whatsapp_number: event.target.value })} placeholder="5350000000" /></label>
              <label>Tarjeta BPA<input value={settings.bpa_card_number} onChange={(event) => setSettings({ ...settings, bpa_card_number: event.target.value })} placeholder="0000-0000-0000-0000" /></label>
              <label>Cuenta Zelle (correo o teléfono)<input value={settings.zelle_account} onChange={(event) => setSettings({ ...settings, zelle_account: event.target.value })} /></label>
              <label>Instrucciones BPA<textarea rows="2" value={settings.bpa_instructions} onChange={(event) => setSettings({ ...settings, bpa_instructions: event.target.value })} /></label>
              <label>Instrucciones saldo móvil<textarea rows="2" value={settings.mobile_balance_instructions} onChange={(event) => setSettings({ ...settings, mobile_balance_instructions: event.target.value })} /></label>
              <label>Instrucciones Zelle<textarea rows="2" value={settings.zelle_instructions} onChange={(event) => setSettings({ ...settings, zelle_instructions: event.target.value })} /></label>
              <label>Instrucciones de recogida<textarea rows="2" value={settings.pickup_instructions} onChange={(event) => setSettings({ ...settings, pickup_instructions: event.target.value })} /></label>
              <label>Política de cambios y devoluciones<textarea rows="2" value={settings.returns_policy} onChange={(event) => setSettings({ ...settings, returns_policy: event.target.value })} /></label>
              <button className="primary-button" disabled={busy}>{busy ? "Guardando…" : "Guardar datos"}</button>
            </form>
          </section>
        )}
      </>}
    </main>
  );
}

export default OwnerDashboard;
