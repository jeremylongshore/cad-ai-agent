export default function OperationList({ operations, selectedOps, onToggleOp }) {
  if (!operations || operations.length === 0) return null;

  return (
    <div className="op-list">
      <h4 className="op-list__title">Operations ({selectedOps.length}/{operations.length} selected)</h4>
      {operations.map((op, i) => (
        <label key={i} className="op-item">
          <input
            type="checkbox"
            className="op-item__checkbox"
            checked={selectedOps.includes(i)}
            onChange={() => onToggleOp(i)}
          />
          <span className="op-item__text">{op.description || op.summary || `Operation ${i + 1}`}</span>
          <span className={`op-item__type op-item__type--${typeClass(op.op_type)}`}>
            {op.op_type}
          </span>
        </label>
      ))}
    </div>
  );
}

function typeClass(opType) {
  if (!opType) return 'edit';
  const t = opType.toLowerCase();
  if (t.includes('move')) return 'move';
  if (t.includes('delete')) return 'delete';
  if (t.includes('add')) return 'add';
  return 'edit';
}
