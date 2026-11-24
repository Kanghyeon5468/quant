'use client';
import {useEffect,useRef} from 'react';
import * as echarts from 'echarts/core';
import {LineChart,BarChart,PieChart,HeatmapChart} from 'echarts/charts';
import {GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,VisualMapComponent} from 'echarts/components';
import {CanvasRenderer} from 'echarts/renderers';
echarts.use([LineChart,BarChart,PieChart,HeatmapChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,VisualMapComponent,CanvasRenderer]);
export default function Chart({option,height=300}: {option:echarts.EChartsCoreOption,height?:number}) {
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!ref.current)return;
    const chart=echarts.init(ref.current,undefined,{renderer:'canvas'});
    chart.setOption({backgroundColor:'transparent',color:['#64d9c7','#8194ff','#edb967','#ef849c'],textStyle:{color:'#9ba8bd',fontFamily:'system-ui'},...option});
    const resize=new ResizeObserver(()=>chart.resize());resize.observe(ref.current);
    return ()=>{resize.disconnect();chart.dispose();};
  },[option]);
  return <div ref={ref} style={{height,width:'100%'}} role="img" aria-label="QuantCore research chart"/>;
}
