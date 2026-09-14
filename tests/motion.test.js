const assert=require('node:assert/strict');
const {position}=require('../web/motion.js');
let directions=new Set(), points=new Set(), diagonal=0;
for(let i=1;i<=24;i++){
 const a=position('F'+i,10,800,500),b=position('F'+i,10.01,800,500);
 assert(Math.hypot(b.x-a.x,b.y-a.y)<3);
 if(Math.abs(b.x-a.x)>0.001&&Math.abs(b.y-a.y)>0.001)diagonal++;
 directions.add(Math.round(Math.atan2(b.y-a.y,b.x-a.x)*4/Math.PI));
 points.add(a.x.toFixed(2)+','+a.y.toFixed(2));
}
assert(points.size===24); assert(diagonal>=20);assert(directions.size>=5);
console.log(JSON.stringify({residents:24,unique_positions:points.size,diagonal,direction_buckets:directions.size}));
