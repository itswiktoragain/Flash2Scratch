from __future__ import annotations
from typing import Any
from .ascode import Expr


class ExpressionMixin:
    def _expr_text(self, expr: Expr | None) -> str:
        if expr is None: return ''
        if expr.kind in ('literal','name','raw'): return str(expr.value)
        if expr.kind == 'call': return f'{expr.value}(...)'
        if expr.kind == 'index': return f'{self._expr_text(expr.left)}[{self._expr_text(expr.args[0]) if expr.args else "0"}]'
        if expr.kind == 'new': return f'new {self._expr_text(expr.left)}'
        if expr.kind == 'binary': return f'({self._expr_text(expr.left)} {expr.value} {self._expr_text(expr.right)})'
        if expr.kind == 'unary': return f'{expr.value}{self._expr_text(expr.left)}'
        return expr.kind

    def _expr_input(self,builder,expr,parent,target_name,locals_map):
        if expr.kind == 'literal':
            v=expr.value
            if isinstance(v,bool): return builder.num(1 if v else 0)
            if isinstance(v,(int,float)): return builder.num(v)
            return builder.text(v)
        if expr.kind == 'name': return self._name_input(builder,str(expr.value),parent,target_name,locals_map)
        if expr.kind == 'binary': return self._binary_input(builder,expr,parent,target_name,locals_map)
        if expr.kind == 'unary':
            if expr.value == '+': return self._expr_input(builder,expr.left or Expr('literal',0),parent,target_name,locals_map)
            if expr.value == '-':
                b=builder.add('operator_subtract',parent=parent); builder.blocks[b]['inputs']['NUM1']=builder.num(0); builder.blocks[b]['inputs']['NUM2']=self._expr_input(builder,expr.left or Expr('literal',0),b,target_name,locals_map); return [2,b]
            if expr.value == '!':
                b=builder.add('operator_not',parent=parent); builder.blocks[b]['inputs']['OPERAND']=self._boolean_input(builder,expr.left or Expr('literal',False),b,target_name,locals_map); return [2,b]
        if expr.kind == 'call': return self._call_expr(builder,expr,parent,target_name,locals_map)
        if expr.kind == 'index':
            if expr.left and expr.left.kind == 'name' and expr.args:
                name=self._var_name(str(expr.left.value),locals_map); self._list_names.add(name); lid=self.p.global_list(name,[]); b=builder.add('data_itemoflist',parent=parent,fields={'LIST':[name,lid]}); idx=Expr('binary',value='+',left=expr.args[0],right=Expr('literal',1)); builder.blocks[b]['inputs']['INDEX']=self._expr_input(builder,idx,b,target_name,locals_map); return [2,b]
            self._unsupported(f'index reporter {self._expr_text(expr)}'); return builder.num(0)
        if expr.kind in ('new','array'):
            self._unsupported('array value used where scalar expected'); return builder.text('')
        if expr.kind == 'ternary':
            self._unsupported(f'ternary reporter {self._expr_text(expr)}'); return self._expr_input(builder,expr.args[0] if expr.args else Expr('literal',0),parent,target_name,locals_map)
        self._unsupported(f'expression {self._expr_text(expr)}'); return builder.num(0)

    def _boolean_input(self,builder,expr,parent,target_name,locals_map):
        if expr.kind == 'literal':
            b=builder.add('operator_equals',parent=parent); builder.blocks[b]['inputs']['OPERAND1']=builder.num(1 if bool(expr.value) else 0); builder.blocks[b]['inputs']['OPERAND2']=builder.num(1); return [2,b]
        result=self._expr_input(builder,expr,parent,target_name,locals_map)
        if isinstance(result,list) and len(result)==2 and isinstance(result[1],str) and result[1] in builder.blocks:
            opcode=builder.blocks[result[1]]['opcode']
            if opcode in {'operator_lt','operator_gt','operator_equals','operator_and','operator_or','operator_not','operator_contains','sensing_keypressed','sensing_touchingobject'}: return result
        b=builder.add('operator_not',parent=parent); inner=builder.add('operator_equals',parent=b); builder.blocks[inner]['inputs']['OPERAND1']=result; builder.blocks[inner]['inputs']['OPERAND2']=builder.num(0); builder.blocks[b]['inputs']['OPERAND']=[2,inner]; return [2,b]

    def _binary_input(self,builder,expr,parent,target_name,locals_map):
        op=str(expr.value); left=expr.left or Expr('literal',0); right=expr.right or Expr('literal',0)
        if op == '+':
            stringy=(left.kind=='literal' and isinstance(left.value,str)) or (right.kind=='literal' and isinstance(right.value,str)); opcode='operator_join' if stringy else 'operator_add'; names=('STRING1','STRING2') if stringy else ('NUM1','NUM2')
        elif op == '-': opcode,names='operator_subtract',('NUM1','NUM2')
        elif op == '*': opcode,names='operator_multiply',('NUM1','NUM2')
        elif op == '/': opcode,names='operator_divide',('NUM1','NUM2')
        elif op == '%': opcode,names='operator_mod',('NUM1','NUM2')
        elif op in ('==','==='): opcode,names='operator_equals',('OPERAND1','OPERAND2')
        elif op in ('!=','!=='): return self._expr_input(builder,Expr('unary',value='!',left=Expr('binary',value='==',left=left,right=right)),parent,target_name,locals_map)
        elif op == '<': opcode,names='operator_lt',('OPERAND1','OPERAND2')
        elif op == '>': opcode,names='operator_gt',('OPERAND1','OPERAND2')
        elif op == '<=': return self._expr_input(builder,Expr('unary',value='!',left=Expr('binary',value='>',left=left,right=right)),parent,target_name,locals_map)
        elif op == '>=': return self._expr_input(builder,Expr('unary',value='!',left=Expr('binary',value='<',left=left,right=right)),parent,target_name,locals_map)
        elif op == '&&': opcode,names='operator_and',('OPERAND1','OPERAND2')
        elif op == '||': opcode,names='operator_or',('OPERAND1','OPERAND2')
        else: self._unsupported(f'binary operator {op}'); return builder.num(0)
        b=builder.add(opcode,parent=parent)
        if op in ('&&','||'):
            builder.blocks[b]['inputs'][names[0]]=self._boolean_input(builder,left,b,target_name,locals_map); builder.blocks[b]['inputs'][names[1]]=self._boolean_input(builder,right,b,target_name,locals_map)
        else:
            builder.blocks[b]['inputs'][names[0]]=self._expr_input(builder,left,b,target_name,locals_map); builder.blocks[b]['inputs'][names[1]]=self._expr_input(builder,right,b,target_name,locals_map)
        return [2,b]

    def _name_input(self,builder,name,parent,target_name,locals_map):
        raw=name.strip()
        if raw in ('_xmouse','_root._xmouse'):
            m=builder.add('sensing_mousex',parent=parent); b=builder.add('operator_add',parent=parent); builder.blocks[m]['parent']=b; builder.blocks[b]['inputs']['NUM1']=[2,m]; builder.blocks[b]['inputs']['NUM2']=builder.num(self.stage_width/2); return [2,b]
        if raw in ('_ymouse','_root._ymouse'):
            m=builder.add('sensing_mousey',parent=parent); b=builder.add('operator_subtract',parent=parent); builder.blocks[m]['parent']=b; builder.blocks[b]['inputs']['NUM1']=builder.num(self.stage_height/2); builder.blocks[b]['inputs']['NUM2']=[2,m]; return [2,b]
        if raw in ('_currentframe','this._currentframe','_root._currentframe'):
            return [2,builder.add('looks_backdropnumbername' if target_name=='stage' else 'looks_costumenumbername',parent=parent,fields={'NUMBER_NAME':['number',None]})]
        if raw in ('_totalframes','this._totalframes','_root._totalframes'): return builder.num(max(self.frame_map.keys(),default=len(self.p.stage.costumes)))
        owner,prop=self._split_property(raw)
        if prop: return self._property_read(builder,owner or 'this',prop,parent,target_name,locals_map)
        if raw.endswith('.length') and '.' in raw:
            base=self._var_name(raw.rsplit('.',1)[0],locals_map)
            if base in self._list_names:
                lid=self.p.global_list(base,[]); return [2,builder.add('data_lengthoflist',parent=parent,fields={'LIST':[base,lid]})]
            b=builder.add('operator_length',parent=parent); builder.blocks[b]['inputs']['STRING']=self._name_input(builder,base,b,target_name,locals_map); return [2,b]
        return self._var_reporter(builder,self._var_name(raw,locals_map),parent)

    def _property_read(self,builder,owner,prop,parent,target_name,locals_map):
        owner=owner.removeprefix('_root.'); current=self._is_current_owner(owner,target_name)
        if current and target_name!='stage':
            if prop=='x':
                m=builder.add('motion_xposition',parent=parent); b=builder.add('operator_add',parent=parent); builder.blocks[m]['parent']=b; builder.blocks[b]['inputs']['NUM1']=[2,m]; builder.blocks[b]['inputs']['NUM2']=builder.num(self.stage_width/2); return [2,b]
            if prop=='y':
                m=builder.add('motion_yposition',parent=parent); b=builder.add('operator_subtract',parent=parent); builder.blocks[m]['parent']=b; builder.blocks[b]['inputs']['NUM1']=builder.num(self.stage_height/2); builder.blocks[b]['inputs']['NUM2']=[2,m]; return [2,b]
            if prop=='rotation':
                m=builder.add('motion_direction',parent=parent); b=builder.add('operator_subtract',parent=parent); builder.blocks[m]['parent']=b; builder.blocks[b]['inputs']['NUM1']=[2,m]; builder.blocks[b]['inputs']['NUM2']=builder.num(90); return [2,b]
            if prop=='scale': return [2,builder.add('looks_size',parent=parent)]
        if not current:
            obj=owner.split('.')[0]; pname={'x':'x position','y':'y position','rotation':'direction','scale':'size'}.get(prop)
            if pname:
                s=builder.add('sensing_of',parent=parent,fields={'PROPERTY':[pname,None]}); builder.blocks[s]['inputs']['OBJECT']=self._menu(builder,s,'sensing_of_object_menu','OBJECT',obj); result=[2,s]
                if prop=='x':
                    b=builder.add('operator_add',parent=parent); builder.blocks[s]['parent']=b; builder.blocks[b]['inputs']['NUM1']=result; builder.blocks[b]['inputs']['NUM2']=builder.num(self.stage_width/2); return [2,b]
                if prop=='y':
                    b=builder.add('operator_subtract',parent=parent); builder.blocks[s]['parent']=b; builder.blocks[b]['inputs']['NUM1']=builder.num(self.stage_height/2); builder.blocks[b]['inputs']['NUM2']=result; return [2,b]
                if prop=='rotation':
                    b=builder.add('operator_subtract',parent=parent); builder.blocks[s]['parent']=b; builder.blocks[b]['inputs']['NUM1']=result; builder.blocks[b]['inputs']['NUM2']=builder.num(90); return [2,b]
                return result
        return self._var_reporter(builder,f'__f2s_state_{owner}_{prop}',parent)

    def _call_expr(self,builder,expr,parent,target_name,locals_map):
        name=str(expr.value); short=name.removeprefix('_root.'); args=expr.args
        if short in ('random','Math.random'):
            r=builder.add('operator_random',parent=parent)
            if short=='random' and args:
                builder.blocks[r]['inputs']['FROM']=builder.num(0); minus=Expr('binary',value='-',left=args[0],right=Expr('literal',1)); builder.blocks[r]['inputs']['TO']=self._expr_input(builder,minus,r,target_name,locals_map); return [2,r]
            builder.blocks[r]['inputs']['FROM']=builder.num(0); builder.blocks[r]['inputs']['TO']=builder.num(1000000); d=builder.add('operator_divide',parent=parent); builder.blocks[r]['parent']=d; builder.blocks[d]['inputs']['NUM1']=[2,r]; builder.blocks[d]['inputs']['NUM2']=builder.num(1000000); return [2,d]
        mmap={'Math.floor':'floor','Math.ceil':'ceiling','Math.abs':'abs','Math.sqrt':'sqrt','Math.sin':'sin','Math.cos':'cos','Math.tan':'tan','Math.asin':'asin','Math.acos':'acos','Math.atan':'atan','Math.log':'ln'}
        if short=='Math.round' and args:
            b=builder.add('operator_round',parent=parent); builder.blocks[b]['inputs']['NUM']=self._expr_input(builder,args[0],b,target_name,locals_map); return [2,b]
        if short in mmap and args:
            b=builder.add('operator_mathop',parent=parent,fields={'OPERATOR':[mmap[short],None]}); builder.blocks[b]['inputs']['NUM']=self._expr_input(builder,args[0],b,target_name,locals_map); return [2,b]
        if short in ('Number','int','String','parseFloat') and args: return self._expr_input(builder,args[0],parent,target_name,locals_map)
        if short=='parseInt' and args:
            b=builder.add('operator_mathop',parent=parent,fields={'OPERATOR':['floor',None]}); builder.blocks[b]['inputs']['NUM']=self._expr_input(builder,args[0],b,target_name,locals_map); return [2,b]
        if short=='getTimer':
            t=builder.add('sensing_timer',parent=parent); b=builder.add('operator_multiply',parent=parent); builder.blocks[t]['parent']=b; builder.blocks[b]['inputs']['NUM1']=[2,t]; builder.blocks[b]['inputs']['NUM2']=builder.num(1000); return [2,b]
        if short=='Key.isDown' and args:
            key=self._key_from_expr_text(self._expr_text(args[0]))
            if key:
                b=builder.add('sensing_keypressed',parent=parent); builder.blocks[b]['inputs']['KEY_OPTION']=self._menu(builder,b,'sensing_keyoptions','KEY_OPTION',key); return [2,b]
        if short.endswith('.hitTest') and args:
            owner=short.rsplit('.',1)[0].removeprefix('_root.'); other=self._expr_text(args[0]).removeprefix('_root.')
            if self._is_current_owner(owner,target_name):
                b=builder.add('sensing_touchingobject',parent=parent); builder.blocks[b]['inputs']['TOUCHINGOBJECTMENU']=self._menu(builder,b,'sensing_touchingobjectmenu','TOUCHINGOBJECTMENU',other); return [2,b]
        self._unsupported(f'reporter call {name}'); return builder.num(0)
